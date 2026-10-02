# API — Sistema de Citas Odontológicas

Referencia completa de la API REST para construir un frontend separado
(web o app). Todo el backend es Django + Django REST Framework; todas
las rutas de acá viven bajo el prefijo `/api/`.

- **Local (dev):** `http://127.0.0.1:8000/api`
- **Servidor:** `http://<host-del-servidor>:<puerto>/api` (a definir
  cuando se despliegue)

## Índice

1. [Convenciones generales](#1-convenciones-generales)
2. [Autenticación (solo doctor/admin)](#2-autenticación-solo-doctoradmin)
3. [Doctores](#3-doctores)
4. [Disponibilidad](#4-disponibilidad)
5. [Horarios semanales y bloqueos (doctor/admin)](#5-horarios-semanales-y-bloqueos-doctoradmin)
6. [Turnos — flujo del paciente (sin login)](#6-turnos--flujo-del-paciente-sin-login)
7. [Turnos — flujo del doctor/admin](#7-turnos--flujo-del-doctoradmin)
8. [Pacientes (doctor/admin)](#8-pacientes-doctoradmin)
9. [CORS: conectar un frontend en otro origen](#9-cors-conectar-un-frontend-en-otro-origen)
10. [Flujos completos de ejemplo](#10-flujos-completos-de-ejemplo)

---

## 1. Convenciones generales

### Quién necesita login y quién no

- **El paciente no tiene cuenta ni login.** Reserva con 4 datos
  básicos (documento, nombre, teléfono, correo) y después usa su
  número de documento como si fuera su "clave" para consultar, editar
  o cancelar su turno. Estos endpoints son **públicos**.
- **El doctor y el administrador sí tienen cuenta** (usuario +
  contraseña) y usan **JWT** (`Authorization: Bearer <token>`) en
  todo lo que gestionan (su agenda, sus pacientes, horarios, etc.).

### Roles y permisos

Lo que puede hacer cada usuario lo deciden los **Permisos y Grupos de
Django**. `role` dice qué tipo de usuario es y asigna solo el grupo:

| Grupo | Puede | No puede |
|---|---|---|
| **Administradores** (`role=ADMIN`) | gestionar usuarios médicos, doctores y horarios | ver pacientes ni historiales clínicos |
| **Doctores** (`role=DOCTOR`) | ver su agenda y sus pacientes, el historial, cargar tratamientos, gestionar su horario | administrar usuarios |

El **superusuario** de Django puede todo. Los permisos de cada grupo se
pueden ajustar desde `/admin/` (Grupos) sin tocar código. Un usuario
**inactivo** (`is_active=false`) no puede iniciar sesión y sus tokens
dejan de funcionar; sus turnos e historial se conservan.

### Límite de intentos (endpoints públicos con CI)

Los endpoints públicos que reciben una CI (reservar, `exists`, mis
consultas, modificar, cancelar) aceptan como máximo
`PUBLIC_CI_RATE_LIMIT` requests por IP (default `30/minute`); al
superarlo responden `429`. Evita recorrer cédulas en masa.

### Formato de fechas

- `date` (solo fecha): `"YYYY-MM-DD"`, ej. `"2026-10-05"`.
- `datetime` (fecha + hora, con timezone): ISO 8601, ej.
  `"2026-10-05T09:00:00-03:00"`. El backend siempre devuelve la hora
  con offset; al mandar una fecha/hora sin timezone se asume la zona
  horaria del servidor.

### Paginación

Los endpoints que listan varios resultados (marcados con 📄 abajo)
devuelven este formato, no un array plano:

```json
{
  "count": 42,
  "next": "http://.../api/doctors/?page=2",
  "previous": null,
  "results": [ /* ... */ ]
}
```

Parámetros: `?page=<n>`. El tamaño de página es fijo (20).

### Errores

- **400** — validación: `{"campo": ["mensaje de error"]}` o
  `{"non_field_errors": ["mensaje"]}`.
- **401** — falta el token o es inválido/expiró:
  `{"detail": "Las credenciales de autenticación no se proveyeron."}`
- **403** — autenticado pero sin permiso: `{"detail": "..."}`
- **404** — no existe: `{"detail": "..."}`

### Filtros, búsqueda y orden

Varios listados soportan `?ordering=campo` (o `-campo` para
descendente), `?search=texto` y filtros por campo exacto — se indican
en cada sección.

---

## 2. Autenticación (solo doctor/admin)

El paciente **nunca** usa esta sección — solo el doctor y el admin.

### `POST /api/auth/login/`

Body:
```json
{ "username": "dra_lopez", "password": "..." }
```
Respuesta `200`:
```json
{ "access": "<jwt>", "refresh": "<jwt>" }
```
`access` dura `ACCESS_TOKEN_LIFETIME_MINUTES` (default 30 min),
`refresh` dura `REFRESH_TOKEN_LIFETIME_DAYS` (default 7 días).
`401` si usuario/contraseña no coinciden.

### `POST /api/auth/refresh/`

Body: `{ "refresh": "<jwt>" }` → Respuesta `200`: `{ "access": "<jwt nuevo>" }`.
(`ROTATE_REFRESH_TOKENS` está activo: idealmente guardá también un
`refresh` nuevo si la respuesta lo trae.)

### `POST /api/auth/logout/`

Body: `{ "refresh": "<jwt>" }` → `200` vacío. Invalida ese refresh
token (no se puede volver a usar). `400` si falta o ya es inválido.

### `GET /api/users/me/`

Con `Authorization: Bearer <access>`. Devuelve:
```json
{
  "id": 3,
  "username": "dra_lopez",
  "email": "lopez@clinica.com",
  "first_name": "Ana",
  "last_name": "López",
  "phone": "099123456",
  "role": "DOCTOR",
  "is_active": true,
  "date_joined": "2026-09-20T10:00:00-03:00",
  "is_admin": false,
  "doctor_id": 1
}
```
- `is_admin`: si administra usuarios (grupo Administradores o superusuario).
- `doctor_id`: su perfil de doctor, o `null` si no tiene (un administrador).

Con esos dos campos el frontend decide qué panel mostrar (no con `role`:
un superusuario puede tener cualquier `role`).

`PATCH /api/users/me/` para editar `first_name`, `last_name`, `phone`,
`email` (el resto es de solo lectura).

### Usuarios médicos (solo administradores)

| Método y ruta | Qué hace |
|---|---|
| `GET /api/users/` 📄 (`?role=DOCTOR\|ADMIN`) | lista doctores, administradores y superusuarios |
| `POST /api/users/` | crea un usuario |
| `GET /api/users/{id}/` | un usuario |
| `PATCH /api/users/{id}/` | edita datos, rol, especialidad, activa/desactiva |
| `PATCH /api/users/{id}/set-password/` | restablece la contraseña |

No hay `DELETE`: a un usuario se lo **desactiva** (`is_active: false`).

`POST` body:
```json
{
  "first_name": "Carlos", "last_name": "Gómez", "username": "dr_gomez",
  "password": "...", "password_confirm": "...",
  "role": "DOCTOR", "specialty": "Pediatría", "appointment_duration_minutes": 30,
  "is_active": true, "email": "", "phone": ""
}
```
Crea la cuenta (contraseña con el hash de Django), el perfil de Doctor y
lo pone en su grupo. `PATCH` acepta los mismos campos menos la
contraseña. Desactivar a un doctor también lo saca de la lista de
doctores para reservar. Respuesta de todas las rutas:
```json
{
  "id": 7, "username": "dr_gomez", "email": "", "first_name": "Carlos", "last_name": "Gómez",
  "phone": "", "role": "DOCTOR", "is_active": true, "is_superuser": false, "is_admin": false,
  "date_joined": "...", "last_login": null,
  "doctor": { "id": 3, "specialty": "Pediatría", "appointment_duration_minutes": 30, "active": true }
}
```
`set-password` body: `{ "new_password": "...", "new_password_confirm": "..." }`.

Para evitar quedarse sin acceso: un administrador no puede desactivarse
ni quitarse el rol a sí mismo, y solo un superusuario puede modificar a
otro superusuario.

### `POST /api/users/register/`

Registro público con `role=PACIENTE`. **No lo necesita el frontend de
pacientes** (el paciente no tiene cuenta); queda por compatibilidad.

---

## 3. Doctores

**Público** para leer (el paciente elige doctor sin login). Escribir
según los permisos de Django sobre Doctor: los administradores crean y
editan; borrar, solo el superusuario (a un doctor se lo desactiva). Para
dar de alta un doctor con su usuario, usar `POST /api/users/`.

### `GET /api/doctors/` 📄

Filtros: `?active=true`, `?specialty=Odontología`.
Búsqueda: `?search=lopez` (busca en nombre/apellido/especialidad).
Orden: `?ordering=created_at` / `?ordering=-created_at`.

Cada resultado:
```json
{
  "id": 1,
  "user": 3,
  "full_name": "Ana López",
  "email": "lopez@clinica.com",
  "specialty": "Odontología general",
  "appointment_duration_minutes": 30,
  "active": true,
  "created_at": "2026-09-20T10:00:00-03:00"
}
```
Quien no administra (paciente anónimo incluido) **solo ve doctores con
`active: true`** en el listado.

### `GET /api/doctors/{id}/`

Mismo shape que arriba, un solo doctor. Público.

### `POST` / `PUT` / `PATCH` / `DELETE /api/doctors/{id}/`

Con token y el permiso correspondiente. `POST`/`PUT`/`PATCH` body: `user` (id de un
`User` con `role=DOCTOR`), `specialty`, `appointment_duration_minutes`,
`active`.

---

## 4. Disponibilidad

**Público**, sin login.

### `GET /api/doctors/{doctor_id}/availability/?date=YYYY-MM-DD`

Devuelve los horarios libres de ese doctor ese día (ya descontando su
horario semanal, bloqueos y turnos ya tomados). **No pagina** — es una
lista simple:

```json
[
  { "start_datetime": "2026-10-05T09:00:00-03:00", "end_datetime": "2026-10-05T09:30:00-03:00" },
  { "start_datetime": "2026-10-05T09:30:00-03:00", "end_datetime": "2026-10-05T10:00:00-03:00" }
]
```
`400` si falta `?date=` o el formato es inválido. `404` si el doctor
no existe o está inactivo. Array vacío `[]` si no hay horarios libres
ese día (no es error).

### `GET /api/doctors/{doctor_id}/available-days/?start=YYYY-MM-DD&end=YYYY-MM-DD`

Días del rango (ambos incluidos, máximo 62 días) con al menos un
horario libre — para marcar en el calendario qué días se pueden
elegir. Usa la misma lógica que el endpoint anterior. No pagina:

```json
[
  { "date": "2026-10-05", "available_slots": 6 },
  { "date": "2026-10-07", "available_slots": 14 }
]
```
Los días sin disponibilidad simplemente no aparecen. `400` si faltan
`start`/`end`, el formato es inválido o el rango es demasiado grande.

---

## 5. Horarios semanales y bloqueos (doctor/admin)

Estos SÍ requieren login (son gestión interna, no los usa el
frontend de pacientes). Qué acción se permite lo deciden los permisos de
Django sobre cada modelo; un doctor solo ve/edita los suyos, un
administrador los de cualquier doctor.

### `GET/POST /api/weekly-schedules/` 📄

Filtros: `?doctor=<id>`, `?weekday=0..6`, `?active=true`.
```json
{ "id": 5, "doctor": 1, "weekday": 0, "weekday_display": "Lunes", "start_time": "09:00:00", "end_time": "12:00:00", "active": true }
```
`weekday`: `0`=lunes … `6`=domingo. Un doctor no manda `doctor` al
crear (se asigna solo, el suyo); un administrador sí debe indicarlo.

`GET/PUT/PATCH/DELETE /api/weekly-schedules/{id}/` — igual esquema.

### `GET/POST /api/availability-exceptions/` 📄

Bloqueos puntuales (vacaciones, feriados, etc.). Filtros: `?doctor=<id>`, `?type=BLOQUEO`.
```json
{ "id": 2, "doctor": 1, "start_datetime": "2026-12-24T00:00:00-03:00", "end_datetime": "2026-12-26T00:00:00-03:00", "type": "BLOQUEO", "reason": "Feriado" }
```
`GET/PUT/PATCH/DELETE /api/availability-exceptions/{id}/` — igual esquema.

---

## 6. Turnos — flujo del paciente (sin login)

Todo esto es **público**: no se manda `Authorization`.

### `POST /api/appointments/` — reservar

Body:
```json
{
  "document_number": "1.234.567-8",
  "name": "Juan Pérez",
  "phone": "099123456",
  "email": "juan@example.com",
  "doctor": 1,
  "start_datetime": "2026-10-05T09:00:00-03:00",
  "notes": "Primera consulta"
}
```
- `document_number`: se normaliza solo (saca puntos, guiones, espacios)
  antes de guardar — podés mandarlo con o sin formato.
- **Paciente existente** (la cédula ya está registrada): alcanza con
  `document_number`, `doctor` y `start_datetime`. `name`/`phone`/`email`
  se ignoran — los datos guardados **no** se sobrescriben.
- **Paciente nuevo**: `name` y `phone` son obligatorios; `email` es
  opcional.
- `notes` es opcional (`""` por defecto) y se usa como **motivo de la
  consulta** (lo ve el doctor en su agenda).

Para saber de antemano si la cédula existe:
`GET /api/patients/{document_number}/exists/` → `{"exists": true, "name": "Juan Pérez"}`
o `{"exists": false}` (público; no expone teléfono ni correo).

Respuesta `201`, un objeto **Appointment**:
```json
{
  "id": 10,
  "patient": "12345678",
  "patient_name": "Juan Pérez",
  "doctor": 1,
  "doctor_name": "Ana López",
  "start_datetime": "2026-10-05T09:00:00-03:00",
  "end_datetime": "2026-10-05T09:30:00-03:00",
  "status": "CONFIRMADA",
  "notes": "Primera consulta",
  "created_at": "2026-09-27T18:00:00-03:00"
}
```
`patient` es directamente el número de documento (es la clave primaria
del paciente). `status` siempre arranca en `"CONFIRMADA"` (no hay
aprobación previa del doctor).

**Errores `400` esperables** (mostralos tal cual al usuario):
- Horario ya no disponible: `{"start_datetime": ["Ese horario ya no está disponible. Elegí otro."]}`
- Ya tiene un turno ese día: `{"non_field_errors": ["Ya tenés una cita agendada ese día. Solo se permite una cita por día."]}`
- Fecha en el pasado: `{"start_datetime": ["No se puede reservar un horario en el pasado."]}`
- Documento inválido: `{"document_number": ["..."]}`

### `GET /api/patients/{document_number}/appointments/` 📄 — mis consultas futuras

Solo las consultas **futuras y pendientes** de esa cédula (no las
pasadas, atendidas ni canceladas), en orden cronológico. Como basta la
CI, devuelve lo mínimo para gestionarlas (**PublicAppointment**, sin
nombre del paciente ni motivo):
```json
{
  "id": 10, "doctor": 1, "doctor_name": "Ana López", "doctor_specialty": "Ortodoncia",
  "start_datetime": "2026-10-18T09:30:00-03:00", "end_datetime": "2026-10-18T10:00:00-03:00",
  "status": "CONFIRMADA", "can_modify": true
}
```
`404` si esa cédula nunca fue registrada.

### `PATCH /api/patients/{document_number}/appointments/{id}/` — modificar

Body (todo opcional):
```json
{ "doctor": 2, "start_datetime": "2026-10-20T10:00:00-03:00", "notes": "..." }
```
- Para **cambiar de doctor** hay que mandar también `start_datetime`
  (los horarios son de cada doctor).
- Revalida la disponibilidad del doctor elegido y el límite de un turno
  por día. El horario anterior queda libre y el recordatorio por correo
  se reprograma.
- **Solo mientras la consulta sea futura y esté pendiente**: si su hora
  ya llegó o pasó responde `400` (`"Esta consulta ya no se puede
  modificar..."`), aunque el frontend haya mostrado el botón.

Devuelve el **PublicAppointment** actualizado. `404` si esa cédula no
tiene esa cita.

### `PATCH /api/patients/{document_number}/appointments/{id}/cancel/` — cancelar

Sin body (o `{}`). Pasa la cita a `CANCELADA` y libera el horario.
Misma regla que modificar: `400` si ya no está pendiente o su hora ya
llegó. `404` si esa cédula no tiene esa cita. (El portal público no lo
ofrece por ahora.)

---

## 7. Turnos — flujo del doctor/admin

Requieren login.

### `GET /api/appointments/agenda/?date=YYYY-MM-DD` — agenda de un día

- Un doctor ve su propia agenda automáticamente.
- Un usuario con el permiso que además administra (p. ej. el
  superusuario) puede indicar `?doctor=<id>`.
- `date` es opcional (default: hoy).

Respuesta `200` (no pagina, shape fijo):
```json
{
  "date": "2026-10-05",
  "doctor": 1,
  "appointments": [ /* array de Appointment, ver sección 6 */ ]
}
```

### `GET /api/appointments/upcoming/` 📄 — próximas consultas

Consultas pendientes del doctor desde ahora en adelante, en orden
cronológico (array de **Appointment**). Mismo `?doctor=` que la agenda.

### `PATCH /api/appointments/{id}/status/` — marcar atendida / no asistió / cancelar

Body: `{ "status": "ATENDIDA" }` (o `"NO_ASISTIO"` / `"CANCELADA"`).
Solo el doctor dueño de la cita (o un administrador con el permiso).
Devuelve el **Appointment** actualizado. `403` si no.

---

## 8. Pacientes (doctor/admin)

Requieren login. El paciente en sí nunca llama a estos endpoints.

### `GET /api/patients/?search=<nombre o CI>` 📄 — "mis pacientes"

Un doctor ve solo los pacientes con los que tuvo al menos un turno (el
superusuario, todos). El grupo Administradores no tiene acceso a datos
clínicos.
```json
{ "document_number": "12345678", "name": "Juan Pérez", "phone": "099123456", "email": "juan@example.com", "created_at": "2026-09-27T18:00:00-03:00", "last_visit": "2026-09-12T10:00:00-03:00" }
```
`last_visit`: última consulta **atendida** (con cualquier doctor); si
nunca se marcó ninguna, el último turno pasado no cancelado; `null` si
no hay.

### `GET /api/patients/{document_number}/` — ficha completa

Datos del paciente + **todos** sus turnos (con cualquier doctor) + su
historial de tratamientos, en una sola llamada:
```json
{
  "document_number": "12345678",
  "name": "Juan Pérez",
  "phone": "099123456",
  "email": "juan@example.com",
  "created_at": "2026-09-27T18:00:00-03:00",
  "last_visit": "2026-09-12T10:00:00-03:00",
  "appointments": [ /* array de Appointment */ ],
  "treatment_records": [ /* array de TreatmentRecord, ver abajo */ ]
}
```
Un doctor solo puede abrir la ficha de un paciente que tuvo al menos un
turno con él (`403` si no).

### `GET/POST /api/patients/{document_number}/treatments/` 📄 — historial de tratamientos

`GET`: tratamientos de ese paciente, de cualquier doctor (historial
compartido dentro de la clínica), del más reciente al más viejo. Misma
regla de acceso que la ficha.
```json
{ "id": 4, "patient": "12345678", "doctor": 1, "doctor_name": "Ana López", "appointment": 10, "date": "2026-09-12T10:00:00-03:00", "reason": "Control general", "description": "Evolución favorable.", "treatment": "Continuar tratamiento actual.", "created_at": "2026-09-27T18:00:00-03:00" }
```
- `date`: fecha del registro = la de la consulta asociada (`appointment`)
  o, si no tiene, la de carga.
- `reason`: motivo / tipo de consulta (opcional).
- `description`: **observaciones** (obligatorio).
- `treatment`: tratamiento / indicaciones (opcional).

`POST` body: `{ "reason": "...", "description": "...", "treatment": "...", "appointment": 10 }`
(todo opcional salvo `description`; `appointment` tiene que ser un turno
de ese mismo paciente, si no `400`). El doctor logueado queda como autor.

---

## 9. CORS: conectar un frontend en otro origen

El backend usa `django-cors-headers`. Si el nuevo frontend corre en un
origen distinto (por ejemplo `http://localhost:3000` en dev, o un
dominio propio en producción), hay que agregarlo a la variable de
entorno `CORS_ALLOWED_ORIGINS` del backend (`.env`), separado por
comas:

```
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://turnos.tuclinica.com
```

No hace falta `credentials: 'include'` ni cookies — la autenticación
va por header `Authorization: Bearer <token>`, no por cookies de
sesión.

---

## 10. Flujos completos de ejemplo

### A) Paciente reserva un turno (sin login)

1. `GET /api/doctors/?active=true` → elegir un doctor.
2. `GET /api/doctors/{id}/availability/?date=2026-10-05` → elegir un horario libre.
3. `POST /api/appointments/` con los 4 datos del paciente + `doctor` + `start_datetime` elegidos.
4. Guardar en el frontend (o mostrarle al paciente) su `document_number` — es lo único que necesita para volver más adelante.

### B) Paciente consulta y modifica una consulta futura

1. `GET /api/patients/{document_number}/appointments/` → sus consultas futuras.
2. Para modificar una con `can_modify: true`: elegir doctor y horario como en el flujo A (`available-days` + `availability`).
3. `PATCH /api/patients/{document_number}/appointments/{id}/` con `start_datetime` (y `doctor`, si cambia).

### C) Doctor revisa su día e historial de un paciente

1. `POST /api/auth/login/` → guardar `access`/`refresh`.
2. `GET /api/appointments/agenda/?date=2026-10-05` (con `Authorization: Bearer <access>`).
3. Para ver el historial completo de un paciente de esa agenda: `GET /api/patients/{document_number}/`.
4. Para cargar una nota de tratamiento: `POST /api/patients/{document_number}/treatments/` con `{"description": "..."}`.
5. Al terminar la consulta: `PATCH /api/appointments/{id}/status/` con `{"status": "ATENDIDA"}`.
