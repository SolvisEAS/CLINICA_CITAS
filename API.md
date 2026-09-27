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
  "date_joined": "2026-09-20T10:00:00-03:00"
}
```
`role` es uno de `"DOCTOR"` o `"ADMIN"` (el valor `"PACIENTE"` es un
resabio del diseño anterior; ya no se usa en el flujo de reserva).

`PATCH /api/users/me/` para editar `first_name`, `last_name`, `phone`,
`email` (no `role`, `is_active` ni `date_joined`, son de solo lectura).

### `POST /api/users/register/`

Registro público con `role=PACIENTE`. **No lo necesita el frontend de
pacientes** (el paciente no tiene cuenta); queda por compatibilidad.
Los usuarios DOCTOR/ADMIN los crea un administrador desde `/admin/`.

---

## 3. Doctores

**Público** para leer (el paciente elige doctor sin login); solo
**ADMIN** puede crear/editar/borrar.

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
Un usuario anónimo (paciente) o un doctor que no sea ADMIN **solo ve
doctores con `active: true`** en el listado.

### `GET /api/doctors/{id}/`

Mismo shape que arriba, un solo doctor. Público.

### `POST` / `PUT` / `PATCH` / `DELETE /api/doctors/{id}/`

Solo ADMIN (con token). `POST`/`PUT`/`PATCH` body: `user` (id de un
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

---

## 5. Horarios semanales y bloqueos (doctor/admin)

Estos SÍ requieren login (son gestión interna, no los usa el
frontend de pacientes). Un DOCTOR solo ve/edita los suyos; ADMIN, todos.

### `GET/POST /api/weekly-schedules/` 📄

Filtros: `?doctor=<id>`, `?weekday=0..6`, `?active=true`.
```json
{ "id": 5, "doctor": 1, "weekday": 0, "weekday_display": "Lunes", "start_time": "09:00:00", "end_time": "12:00:00", "active": true }
```
`weekday`: `0`=lunes … `6`=domingo. Un DOCTOR no manda `doctor` al
crear (se asigna solo, el suyo); un ADMIN sí debe indicarlo.

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
- `notes` es opcional (`""` por defecto).
- El backend crea o actualiza al paciente por su `document_number`
  (si ya existía, actualiza nombre/teléfono/correo con lo último
  mandado).

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

### `GET /api/patients/{document_number}/appointments/` 📄 — consultar mis turnos

Lista los turnos de ese paciente (todos los estados), orden
descendente por fecha. `404` si esa cédula nunca reservó nada.

### `PATCH /api/patients/{document_number}/appointments/{id}/` — editar / reprogramar

Body (uno o ambos campos, todos opcionales):
```json
{ "start_datetime": "2026-10-06T10:00:00-03:00", "notes": "Cambio de horario" }
```
Revalida disponibilidad y el límite de un turno por día (excluyendo el
turno que se está editando). Devuelve el **Appointment** actualizado.
`400` si la cita ya no está `CONFIRMADA`, ya pasó, o el horario nuevo
no está disponible. `404` si esa cédula no tiene esa cita.

### `PATCH /api/patients/{document_number}/appointments/{id}/cancel/` — cancelar

Sin body (o `{}`). Pasa la cita a `CANCELADA` y libera el horario.
`400` si ya no está `CONFIRMADA` o ya pasó. `404` si esa cédula no
tiene esa cita.

---

## 7. Turnos — flujo del doctor/admin

Requieren login.

### `GET /api/appointments/agenda/?date=YYYY-MM-DD` — agenda de un día

- Un **DOCTOR** ve su propia agenda automáticamente.
- Un **ADMIN** debe indicar `?doctor=<id>` además de `?date=`.
- `date` es opcional (default: hoy).

Respuesta `200` (no pagina, shape fijo):
```json
{
  "date": "2026-10-05",
  "doctor": 1,
  "appointments": [ /* array de Appointment, ver sección 6 */ ]
}
```

### `PATCH /api/appointments/{id}/status/` — marcar atendida / no asistió / cancelar

Body: `{ "status": "ATENDIDA" }` (o `"NO_ASISTIO"` / `"CANCELADA"`).
Solo el doctor dueño de la cita o un ADMIN. Devuelve el **Appointment**
actualizado. `403` si no es el dueño ni admin.

---

## 8. Pacientes (doctor/admin)

Requieren login. El paciente en sí nunca llama a estos endpoints.

### `GET /api/patients/` 📄 — "mis pacientes"

Un **DOCTOR** ve solo los pacientes con los que tuvo al menos un turno;
un **ADMIN** ve todos.
```json
{ "document_number": "12345678", "name": "Juan Pérez", "phone": "099123456", "email": "juan@example.com", "created_at": "2026-09-27T18:00:00-03:00" }
```

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
  "appointments": [ /* array de Appointment */ ],
  "treatment_records": [ /* array de TreatmentRecord, ver abajo */ ]
}
```
Un **DOCTOR** solo puede abrir la ficha de un paciente que tuvo al
menos un turno con él (`403` si no). Un **ADMIN** ve cualquiera.

### `GET/POST /api/patients/{document_number}/treatments/` 📄 — historial de tratamientos

`GET`: lista de tratamientos de ese paciente (de cualquier doctor —
historial clínico compartido dentro de la clínica).
```json
{ "id": 4, "patient": "12345678", "doctor": 1, "doctor_name": "Ana López", "appointment": 10, "description": "Limpieza dental de rutina", "created_at": "2026-09-27T18:00:00-03:00" }
```
`POST` body: `{ "description": "...", "appointment": 10 }` (`appointment`
opcional). Un **DOCTOR** queda asignado automáticamente como autor; un
**ADMIN** debe mandar además `"doctor": <id>` en el body.

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

### B) Paciente vuelve a consultar/cancelar

1. `GET /api/patients/{document_number}/appointments/` → mostrar su lista de turnos.
2. Si quiere cancelar: `PATCH /api/patients/{document_number}/appointments/{id}/cancel/`.
3. Si quiere reprogramar: repetir el paso 2 del flujo A para elegir nuevo horario, después `PATCH /api/patients/{document_number}/appointments/{id}/` con el `start_datetime` nuevo.

### C) Doctor revisa su día e historial de un paciente

1. `POST /api/auth/login/` → guardar `access`/`refresh`.
2. `GET /api/appointments/agenda/?date=2026-10-05` (con `Authorization: Bearer <access>`).
3. Para ver el historial completo de un paciente de esa agenda: `GET /api/patients/{document_number}/`.
4. Para cargar una nota de tratamiento: `POST /api/patients/{document_number}/treatments/` con `{"description": "..."}`.
5. Al terminar la consulta: `PATCH /api/appointments/{id}/status/` con `{"status": "ATENDIDA"}`.
