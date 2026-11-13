// Веб-интерфейс автопарка. Все запросы идут через шлюз (/api/...).

let session = JSON.parse(sessionStorage.getItem("session") || "null");
let vehicles = [];
let drivers = [];

const $ = (id) => document.getElementById(id);

// ---------- Общие функции ----------

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (session) options.headers["Authorization"] = "Bearer " + session.token;
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch("/api/" + path, options);
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && session) logout();
  if (!response.ok) throw new Error(errorText(data));
  return data;
}

// Сервисы возвращают причину отказа в поле detail
function errorText(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return "Проверьте заполнение полей: " + data.detail.map((item) => item.msg).join("; ");
  return "Не удалось выполнить действие";
}

function showMessage(text, success = false) {
  const box = $("message");
  box.textContent = text;
  box.className = success ? "message success" : "message";
  box.hidden = false;
  clearTimeout(showMessage.timer);
  showMessage.timer = setTimeout(() => (box.hidden = true), 8000);
}

// Текст из базы вставляем в страницу только через эту функцию, чтобы он не мог стать HTML-кодом
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

// "2026-11-09T09:00:00+03:00" -> "09.11.2026 09:00"
function formatTime(value) {
  if (!value) return "—";
  const [date, time] = value.split("T");
  const [year, month, day] = date.split("-");
  return `${day}.${month}.${year} ${time.slice(0, 5)}`;
}

function badge(text, kind) {
  return `<span class="badge ${kind}">${text}</span>`;
}

function fillTable(bodyId, rows, columnsCount) {
  $(bodyId).innerHTML = rows.length
    ? rows.join("")
    : `<tr><td class="empty" colspan="${columnsCount}">Пока пусто</td></tr>`;
}

// Пустое поле времени означает "сейчас"
function timeOrNull(value) {
  return value ? value : null;
}

// ---------- Вход и выход ----------

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    session = await api("POST", "login", { login: $("login-name").value, password: $("login-password").value });
    sessionStorage.setItem("session", JSON.stringify(session));
    $("login-password").value = "";
    $("login-error").textContent = "";
    showApp();
  } catch (error) {
    session = null;
    $("login-error").textContent = error.message;
  }
});

function logout() {
  session = null;
  sessionStorage.removeItem("session");
  $("app").hidden = true;
  $("login-screen").hidden = false;
}
$("logout").addEventListener("click", logout);

function showApp() {
  $("login-screen").hidden = true;
  $("app").hidden = false;
  $("user-name").textContent = session.name;
  // Формы и вкладки показываем только той роли, которой они разрешены
  document.querySelectorAll("[data-role]").forEach((element) => {
    element.hidden = element.dataset.role !== session.role;
  });
  openTab("vehicles");
}

// ---------- Вкладки ----------

const loaders = { vehicles: loadFleet, drivers: loadFleet, trips: loadTrips, orders: loadOrders, reports: () => {} };

async function openTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => (tab.hidden = tab.id !== "tab-" + name));
  document.querySelectorAll("#tabs button").forEach((button) =>
    button.classList.toggle("active", button.dataset.tab === name));
  try {
    await loaders[name]();
  } catch (error) {
    showMessage(error.message);
  }
}

$("tabs").addEventListener("click", (event) => {
  if (event.target.dataset.tab) openTab(event.target.dataset.tab);
});

// ---------- Машины и водители ----------

async function loadFleet() {
  let busy = { vehicles: {}, drivers: {} };
  let orders = [];
  [vehicles, drivers] = await Promise.all([api("GET", "fleet/vehicles"), api("GET", "fleet/drivers")]);
  // Если сервис поездок или обслуживания недоступен, справочник всё равно показываем
  try {
    busy = await api("GET", "trips/status");
    orders = await api("GET", "maintenance/orders?status=in_progress");
  } catch (error) {
    showMessage("Состояние машин может быть неточным: " + error.message);
  }
  const inService = new Set(orders.map((order) => order.vehicle_id));
  const isAdmin = session.role === "admin";

  fillTable("vehicles-body", vehicles.map((vehicle) => {
    let state = badge("свободна", "ok");
    if (!vehicle.active) state = badge("списана", "");
    else if (busy.vehicles[vehicle.id] === "on_trip") state = badge("в поездке", "busy");
    else if (inService.has(vehicle.id)) state = badge("на обслуживании", "warn");
    else if (busy.vehicles[vehicle.id] === "needs_service") state = badge("ждёт обслуживания", "bad");
    const action = isAdmin
      ? `<button class="small secondary" data-toggle="vehicles" data-id="${vehicle.id}" data-active="${vehicle.active}">
           ${vehicle.active ? "Списать" : "Вернуть"}</button>` : "";
    return `<tr><td>${escapeHtml(vehicle.plate)}</td><td>${escapeHtml(vehicle.model)}</td>
            <td>${vehicle.category}</td><td>${state}</td><td>${action}</td></tr>`;
  }), 5);

  fillTable("drivers-body", drivers.map((driver) => {
    let state = badge("свободен", "ok");
    if (!driver.active) state = badge("уволен", "");
    else if (busy.drivers[driver.id]) state = badge("в поездке", "busy");
    const action = isAdmin
      ? `<button class="small secondary" data-toggle="drivers" data-id="${driver.id}" data-active="${driver.active}">
           ${driver.active ? "Уволить" : "Вернуть"}</button>` : "";
    return `<tr><td>${escapeHtml(driver.full_name)}</td><td>${escapeHtml(driver.license_number)}</td>
            <td>${driver.categories.join(", ")}</td><td>${state}</td><td>${action}</td></tr>`;
  }), 5);
}

$("vehicle-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("POST", "fleet/vehicles", Object.fromEntries(form));
    event.target.reset();
    showMessage("Машина добавлена", true);
    await loadFleet();
  } catch (error) {
    showMessage(error.message);
  }
});

$("driver-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("POST", "fleet/drivers", {
      full_name: form.get("full_name"),
      license_number: form.get("license_number"),
      categories: form.getAll("cat"),
    });
    event.target.reset();
    showMessage("Водитель добавлен", true);
    await loadFleet();
  } catch (error) {
    showMessage(error.message);
  }
});

// Кнопки "Списать" / "Уволить" / "Вернуть"
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-toggle]");
  if (!button) return;
  try {
    await api("PATCH", `fleet/${button.dataset.toggle}/${button.dataset.id}`,
      { active: button.dataset.active !== "true" });
    await loadFleet();
  } catch (error) {
    showMessage(error.message);
  }
});

// ---------- Поездки ----------

async function loadTrips() {
  let trips;
  [vehicles, drivers, trips] = await Promise.all([
    api("GET", "fleet/vehicles"), api("GET", "fleet/drivers"), api("GET", "trips/trips"),
  ]);
  $("trip-vehicle").innerHTML = '<option value="">Машина…</option>' + vehicles
    .filter((vehicle) => vehicle.active)
    .map((vehicle) => `<option value="${vehicle.id}">${escapeHtml(vehicle.plate)} · ${escapeHtml(vehicle.model)} (${vehicle.category})</option>`)
    .join("");
  $("trip-driver").innerHTML = '<option value="">Водитель…</option>' + drivers
    .filter((driver) => driver.active)
    .map((driver) => `<option value="${driver.id}">${escapeHtml(driver.full_name)} (${driver.categories.join(", ")})</option>`)
    .join("");

  const isDispatcher = session.role === "dispatcher";
  fillTable("trips-body", trips.map((trip) => {
    const active = trip.status === "active";
    const serviced = active ? "—" : (trip.serviced_at ? badge("да", "ok") : badge("нет", "bad"));
    const action = active && isDispatcher
      ? `<button class="small" data-finish="${trip.id}">Принять машину</button>` : "";
    return `<tr><td>${trip.id}</td><td>${escapeHtml(trip.vehicle_plate)}</td><td>${escapeHtml(trip.driver_name)}</td>
            <td>${escapeHtml(trip.purpose)}</td><td>${formatTime(trip.started_at)}</td>
            <td>${active ? badge("в поездке", "busy") : formatTime(trip.finished_at)}</td>
            <td>${trip.distance_km ?? "—"}</td><td>${serviced}</td><td>${action}</td></tr>`;
  }), 9);
}

$("trip-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("POST", "trips/trips", {
      vehicle_id: Number(form.get("vehicle_id")),
      driver_id: Number(form.get("driver_id")),
      purpose: form.get("purpose"),
      at: timeOrNull(form.get("at")),
    });
    event.target.reset();
    showMessage("Машина выпущена в поездку", true);
    await loadTrips();
  } catch (error) {
    showMessage(error.message);
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-finish]");
  if (!button) return;
  const distance = prompt("Пробег за поездку, км:");
  if (distance === null) return;
  const at = prompt("Время возвращения в виде 2026-11-09T12:30 (пусто — сейчас):", "");
  if (at === null) return;
  try {
    await api("POST", `trips/trips/${button.dataset.finish}/finish`,
      { distance_km: Number(distance.replace(",", ".")), at: timeOrNull(at.trim()) });
    showMessage("Поездка закрыта, машина отправлена на обслуживание", true);
    await loadTrips();
  } catch (error) {
    showMessage(error.message);
  }
});

// ---------- Обслуживание ----------

const ORDER_STATES = {
  waiting: badge("ждёт механика", "bad"),
  in_progress: badge("в работе", "warn"),
  done: badge("выполнено", "ok"),
};

async function loadOrders() {
  const [orders, hours] = await Promise.all([api("GET", "maintenance/orders"), api("GET", "maintenance/working-hours")]);
  $("working-hours").textContent =
    `Сервис работает: ${hours.days}, ${hours.from}–${hours.to}. Сейчас ${hours.open_now ? "открыт" : "закрыт"}.`;

  const isMechanic = session.role === "mechanic";
  fillTable("orders-body", orders.map((order) => {
    let action = "";
    if (isMechanic && order.status === "waiting") action = `<button class="small" data-order="${order.id}" data-action="start">Начать</button>`;
    if (isMechanic && order.status === "in_progress") action = `<button class="small" data-order="${order.id}" data-action="finish">Завершить</button>`;
    return `<tr><td>${order.id}</td><td>${escapeHtml(order.vehicle_plate)}</td><td>${ORDER_STATES[order.status]}</td>
            <td>${formatTime(order.created_at)}</td><td>${formatTime(order.started_at)}</td>
            <td>${formatTime(order.finished_at)}</td><td>${escapeHtml(order.mechanic || "—")}</td><td>${action}</td></tr>`;
  }), 8);
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-order]");
  if (!button) return;
  try {
    await api("POST", `maintenance/orders/${button.dataset.order}/${button.dataset.action}`,
      { at: timeOrNull($("order-at").value) });
    showMessage(button.dataset.action === "start" ? "Обслуживание начато" : "Обслуживание завершено, машину можно выпускать", true);
    await loadOrders();
  } catch (error) {
    showMessage(error.message);
  }
});

// ---------- Отчёты ----------

$("report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const query = `from=${form.get("from")}&to=${form.get("to")}`;
  try {
    const [byVehicles, byDrivers] = await Promise.all([
      api("GET", "reports/vehicles?" + query), api("GET", "reports/drivers?" + query),
    ]);
    fillTable("report-vehicles-body", byVehicles.rows.map((row) =>
      `<tr><td>${escapeHtml(row.vehicle_plate)}</td><td>${row.trips_count}</td><td>${row.distance_km}</td>
       <td>${row.hours_on_trips}</td><td>${row.hours_waiting_service}</td><td>${row.hours_in_service}</td>
       <td>${row.utilization_percent}</td></tr>`), 7);
    fillTable("report-drivers-body", byDrivers.rows.map((row) => {
      const days = Object.entries(row.hours_by_day)
        .map(([day, hours]) => `${day.slice(8)}.${day.slice(5, 7)}: ${hours} ч`).join("<br>");
      return `<tr><td>${escapeHtml(row.driver_name)}</td><td>${row.trips_count}</td>
              <td>${row.hours_worked}</td><td>${row.distance_km}</td><td>${days}</td></tr>`;
    }), 5);
  } catch (error) {
    showMessage(error.message);
  }
});

// ---------- Запуск ----------

if (session) showApp();
