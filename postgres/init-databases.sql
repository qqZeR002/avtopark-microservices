-- Выполняется один раз при первом запуске PostgreSQL.
-- Создаёт отдельную базу и отдельного пользователя для каждого сервиса,
-- чтобы сервис физически не мог прочитать чужие данные.

-- пароль берём из переменной окружения контейнера
\getenv service_password SERVICE_DB_PASSWORD

CREATE USER fleet_user WITH PASSWORD :'service_password';
CREATE DATABASE fleet_db OWNER fleet_user;
REVOKE ALL ON DATABASE fleet_db FROM PUBLIC;

CREATE USER trips_user WITH PASSWORD :'service_password';
CREATE DATABASE trips_db OWNER trips_user;
REVOKE ALL ON DATABASE trips_db FROM PUBLIC;

CREATE USER maintenance_user WITH PASSWORD :'service_password';
CREATE DATABASE maintenance_db OWNER maintenance_user;
REVOKE ALL ON DATABASE maintenance_db FROM PUBLIC;

CREATE USER reports_user WITH PASSWORD :'service_password';
CREATE DATABASE reports_db OWNER reports_user;
REVOKE ALL ON DATABASE reports_db FROM PUBLIC;
