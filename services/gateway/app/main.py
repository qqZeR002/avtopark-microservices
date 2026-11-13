"""Шлюз - единственная точка входа в систему.

Что делает:
1. Проверяет логин и пароль, выдаёт токен (ФТ-13).
2. Проверяет, что роль пользователя разрешает действие.
3. Пересылает запрос нужному сервису.
4. Отдаёт страницы веб-интерфейса.
"""
import hmac
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

JWT_SECRET = os.environ["JWT_SECRET"]
TOKEN_HOURS = 8

# Адреса внутренних сервисов (снаружи они недоступны)
SERVICES = {
    "fleet": os.getenv("FLEET_URL", "http://fleet:8000"),
    "trips": os.getenv("TRIPS_URL", "http://trips:8000"),
    "maintenance": os.getenv("MAINTENANCE_URL", "http://maintenance:8000"),
    "reports": os.getenv("REPORTS_URL", "http://reports:8000"),
}

SERVICE_NAMES = {
    "fleet": "справочников",
    "trips": "поездок",
    "maintenance": "обслуживания",
    "reports": "отчётов",
}

# Четыре пользователя, по одному на роль. Пароли приходят из переменных окружения.
USERS = {
    "admin": {"role": "admin", "name": "Администратор", "password": os.environ["ADMIN_PASSWORD"]},
    "dispatcher": {"role": "dispatcher", "name": "Диспетчер", "password": os.environ["DISPATCHER_PASSWORD"]},
    "mechanic": {"role": "mechanic", "name": "Механик", "password": os.environ["MECHANIC_PASSWORD"]},
    "manager": {"role": "manager", "name": "Руководитель", "password": os.environ["MANAGER_PASSWORD"]},
}

ALL_ROLES = {"admin", "dispatcher", "mechanic", "manager"}

# Кто может изменять данные в каждом сервисе
WRITE_ROLES = {
    "fleet": {"admin"},
    "trips": {"dispatcher"},
    "maintenance": {"mechanic"},
}

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Автопарк: шлюз")
http_client = httpx.AsyncClient(timeout=10)


class LoginRequest(BaseModel):
    login: str
    password: str


def allowed_roles(service: str, method: str) -> set[str]:
    if service == "reports":
        return {"manager"}
    if method == "GET":
        return ALL_ROLES
    return WRITE_ROLES.get(service, set())


def read_token(request: Request) -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Нужно войти в систему")
    try:
        return jwt.decode(header.removeprefix("Bearer "), JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Сессия истекла или токен неверный, войдите заново")


@app.post("/api/login")
def login(body: LoginRequest):
    user = USERS.get(body.login)
    # compare_digest сравнивает строки за одинаковое время, чтобы пароль нельзя было подобрать по задержке
    if user is None or not hmac.compare_digest(user["password"].encode(), body.password.encode()):
        raise HTTPException(401, "Неверный логин или пароль")
    payload = {
        "sub": body.login,
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return {"token": token, "login": body.login, "role": user["role"], "name": user["name"]}


@app.get("/health")
def gateway_health():
    return {"status": "ok", "service": "gateway"}


@app.get("/api/health")
async def health():
    """Состояние всех сервисов - удобно показывать, что отказ одного не роняет остальные."""
    result = {"gateway": "ok"}
    for name, url in SERVICES.items():
        try:
            response = await http_client.get(f"{url}/health", timeout=2)
            result[name] = "ok" if response.status_code == 200 else "error"
        except httpx.HTTPError:
            result[name] = "недоступен"
    return result


@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PATCH"])
async def proxy(service: str, path: str, request: Request):
    if service not in SERVICES:
        raise HTTPException(404, "Такого раздела нет")

    user = read_token(request)
    if user["role"] not in allowed_roles(service, request.method):
        raise HTTPException(403, "Это действие недоступно для вашей роли")

    try:
        response = await http_client.request(
            request.method,
            f"{SERVICES[service]}/{path}",
            params=request.query_params,
            content=await request.body(),
            headers={"Content-Type": "application/json", "X-User": user["sub"]},
        )
    except httpx.HTTPError:
        raise HTTPException(503, f"Сервис {SERVICE_NAMES[service]} временно недоступен")

    return Response(content=response.content, status_code=response.status_code,
                    media_type=response.headers.get("content-type"))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
