# Sistema de Citas Odontológicas — MVP

Backend en Django + Django REST Framework para el sistema de gestión y
reserva de citas descrito en el documento base del proyecto. Es un
proyecto **independiente** de SOLVIS_CRM — otro dominio de negocio
(pacientes/doctores/citas en vez de empresas/leads/oportunidades) — y
se instala aparte, en otro puerto del mismo servidor cuando llegue el
momento de desplegarlo.

## Decisiones tomadas para este MVP

- **Duración de citas fija por doctor** (`Doctor.appointment_duration_minutes`),
  no variable por tipo de tratamiento. Se puede migrar a duración
  variable más adelante sin rehacer el núcleo.
- **Confirmación automática**: una cita queda `CONFIRMADA` apenas el
  paciente reserva un horario disponible, sin aprobación previa del
  doctor.
- **Prevención de doble reserva a nivel de base de datos**: además de
  validar en el backend antes de confirmar, PostgreSQL tiene una
  restricción (`ExclusionConstraint`) que hace *físicamente imposible*
  que existan dos citas activas del mismo doctor con horarios
  solapados, incluso si dos pacientes reservan casi al mismo tiempo.
  Esto se probó a propósito durante el desarrollo (ver sección de
  verificación más abajo).
- **Notificaciones**: por ahora solo por **email** (confirmación +
  1 recordatorio, configurable, por defecto 24hs antes). El modelo ya
  distingue un canal `WHATSAPP` para cuando se defina el proveedor,
  pero no está implementado todavía — el documento base lo marca
  explícitamente como una integración a resolver aparte.
- **No incluye todavía** (quedan para una fase siguiente, tal como
  sugiere el documento): historia clínica, ficha odontológica, pagos,
  facturación, reportes avanzados, Google Calendar, WhatsApp.

## Roles

- **Paciente**: se registra solo, reserva/cancela sus propias citas.
- **Doctor**: lo crea un administrador desde `/admin/` (usuario con
  `role=DOCTOR` + un perfil en el modelo `Doctor`). Gestiona su propio
  horario semanal, sus bloqueos, y su agenda.
- **Administrador**: gestiona doctores, horarios y usuarios desde
  `/admin/`.

## 1. Requisitos previos

- Python 3.10+
- PostgreSQL instalado localmente (sin Docker — ver más abajo)

## 2. Puesta en marcha

### 2.1 Crear la base de datos

Abrí **SQL Shell (psql)** (o `psql` desde la terminal) conectado como
superusuario y ejecutá:

```sql
CREATE USER clinica WITH PASSWORD 'clinica_dev_password';
CREATE DATABASE clinica_citas OWNER clinica;
```

No hace falta crear ninguna extensión a mano — la migración inicial
del proyecto la instala sola (`btree_gist`, necesaria para la
restricción anti-doble-reserva).

### 2.2 Entorno virtual e instalación

```powershell
cd C:\ruta\a\CLINICA_CITAS
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements\development.txt
```

### 2.3 Variables de entorno

```powershell
copy .env.example .env
```

Generá una `DJANGO_SECRET_KEY` propia:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

y pegala en el `.env`. El resto de los valores por defecto (usuario,
contraseña, puerto de Postgres) ya coinciden con el paso 2.1.

### 2.4 Migrar y crear el administrador

```powershell
python manage.py migrate
python manage.py createsuperuser
```

Con ese superusuario después vas a poder entrar a `/admin/` y también
conviene asignarle `role = Administrador` desde ahí mismo (Django lo
deja con `role=Paciente` por defecto al crearlo por consola).

### 2.5 Levantar el servidor

```powershell
python manage.py runserver
```

## 3. Cargar el primer doctor y su horario

Por ahora esto se hace desde `/admin/` (http://127.0.0.1:8000/admin/):

1. **Usuarios** → agregar uno nuevo con `role = Doctor`.
2. **Doctores** → crear un perfil vinculado a ese usuario, con su
   especialidad y la duración fija de sus turnos (en minutos).
3. **Horarios** → **Horarios** semanales → agregar uno por cada bloque
   que trabaje ese doctor (por ejemplo, lunes 08:00–12:00 y
   14:00–18:00).
4. Opcionalmente, **Excepciones de disponibilidad** para bloquear un
   día puntual (vacaciones, feriado, etc.).

## 4. Probar la API (checklist)

Guardá el token de un login en una variable:

```powershell
$TOKEN = (curl -Method POST http://127.0.0.1:8000/api/auth/login/ -ContentType "application/json" -Body '{"username":"tu_usuario","password":"tu_clave"}').access
```

(o usá `curl`/Postman como prefieras)

- [ ] **Registro de paciente**: `POST /api/users/register/`
- [ ] **Login**: `POST /api/auth/login/` devuelve `access` + `refresh`
- [ ] **Listar doctores**: `GET /api/doctors/`
- [ ] **Disponibilidad**: `GET /api/doctors/<id>/availability/?date=YYYY-MM-DD`
      devuelve los horarios libres, ya descontando el horario semanal,
      los bloqueos y las citas existentes.
- [ ] **Reservar**: `POST /api/appointments/` con `{"doctor": <id>, "start_datetime": "..."}`
      → la cita queda `CONFIRMADA` al instante.
- [ ] **Doble reserva rechazada**: reservar el mismo horario de nuevo
      devuelve `400` con "Ese horario ya no está disponible."
- [ ] **Mis citas**: `GET /api/appointments/mine/`
- [ ] **Agenda del doctor**: `GET /api/appointments/agenda/?date=YYYY-MM-DD`
      (con el token del doctor)
- [ ] **Cancelar**: `PATCH /api/appointments/<id>/cancel/` (paciente,
      su propia cita) → el horario vuelve a aparecer en disponibilidad.
- [ ] **Marcar atendida/no asistió**: `PATCH /api/appointments/<id>/status/`
      con `{"status": "ATENDIDA"}` (doctor dueño de la cita o admin).
- [ ] **Notificaciones**: correr `python manage.py send_pending_notifications`
      envía la confirmación pendiente (en desarrollo se imprime en la
      consola del servidor en vez de mandarse de verdad — ver `.env`).

Ya probé cada uno de estos puntos en mi entorno antes de entregarte el
proyecto, incluyendo un intento deliberado de doble reserva simultánea
para confirmar que la base de datos la rechaza.

## 5. El worker de recordatorios

`send_pending_notifications` es un comando de Django, no un proceso
que quede corriendo solo. En el servidor de producción hay que
programarlo con `cron` para que se ejecute cada pocos minutos, por
ejemplo:

```
*/5 * * * * cd /ruta/al/proyecto && venv/bin/python manage.py send_pending_notifications >> /var/log/clinica_notifications.log 2>&1
```

Esto lo armamos juntos cuando lleguemos al paso de desplegarlo en el
servidor de UpCloud.

## 6. Correo real (en vez de la consola)

Mientras `EMAIL_BACKEND=console` (valor por defecto en `.env`), los
emails no se envían de verdad — se imprimen en la terminal donde corre
el servidor, para poder probar sin tener todavía una cuenta de correo
configurada. Cuando quieran que se envíen de verdad, cambiá en `.env`:

```
EMAIL_BACKEND=smtp
EMAIL_HOST=...
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
```

## 7. Estructura del proyecto

```
CLINICA_CITAS/
  config/           -> settings por entorno, urls
  core/             -> permisos compartidos por rol
  apps/
    users/          -> usuario personalizado, registro, login/JWT
    doctors/        -> perfil de doctor
    schedules/      -> horario semanal, bloqueos, cálculo de disponibilidad
    appointments/   -> reserva de citas, agenda, cancelación
    notifications/  -> registro y envío de confirmaciones/recordatorios
  requirements/
```

## 8. Siguiente paso

Cuando confirmes que todo funciona en tu computadora, seguimos con el
despliegue en el servidor de UpCloud (otro puerto, junto a Odoo y a
SOLVIS_CRM, con Nginx como reverse proxy) y con cerrar las decisiones
que todavía quedan abiertas del documento base: si se requiere
verificación de correo/teléfono al registrarse, qué feriados
contemplar, y la integración de WhatsApp cuando definan el proveedor.
