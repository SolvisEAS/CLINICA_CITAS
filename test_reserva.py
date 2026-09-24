#!/usr/bin/env python3
"""
Script de prueba: simula lo que haría un paciente real contra la API
ya desplegada en el servidor. Solo usa la librería estándar de Python
(no hace falta instalar nada nuevo en el venv).

Uso:
    python3 test_reserva.py <usuario> <contraseña>

Ejemplo:
    python3 test_reserva.py paciente_prueba PruebaSegura123!

Qué hace, paso a paso:
    1. Inicia sesión con el paciente que ya registraste manualmente.
    2. Lista los doctores disponibles.
    3. Busca el primer día (de los próximos 14) en que ese doctor
       tenga al menos un horario libre.
    4. Reserva ese horario.
    5. Confirma que la cita quedó en "Mis citas".
    6. Intenta reservar el MISMO horario de nuevo, a propósito, para
       comprobar que el sistema lo rechaza (no permite doble reserva).
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://95.111.213.227:8001/api"


def call(method, path, data=None, token=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    if len(sys.argv) != 3:
        print("Uso: python3 test_reserva.py <usuario> <contraseña>")
        sys.exit(1)

    username, password = sys.argv[1], sys.argv[2]

    print("== 1. Login ==")
    status, resp = call("POST", "/auth/login/", {"username": username, "password": password})
    print(status, resp)
    if status != 200:
        print("No se pudo iniciar sesión. Revisá usuario/contraseña.")
        sys.exit(1)
    token = resp["access"]

    print("\n== 2. Lista de doctores ==")
    status, resp = call("GET", "/doctors/", token=token)
    print(status, resp)
    doctores = resp.get("results", resp) if isinstance(resp, dict) else resp
    if not doctores:
        print("No hay ningún doctor cargado todavía. Cargá uno desde /admin/ y volvé a correr el script.")
        sys.exit(1)
    doctor_id = doctores[0]["id"]
    print(f"\nUsando doctor id={doctor_id}")

    print("\n== 3. Buscando el primer día con horarios libres (próximos 14 días) ==")
    slot = None
    for i in range(1, 15):
        d = date.today() + timedelta(days=i)
        status, resp = call("GET", f"/doctors/{doctor_id}/availability/?date={d.isoformat()}", token=token)
        if status == 200 and resp:
            print(f"{d.isoformat()}: {len(resp)} horario(s) libres")
            slot = resp[0]
            break
        else:
            print(f"{d.isoformat()}: sin horarios libres")
    if not slot:
        print("\nNo se encontró ningún horario libre en los próximos 14 días.")
        print("Revisá que el doctor tenga un 'Horario semanal' cargado en /admin/.")
        sys.exit(1)

    print(f"\nHorario elegido: {slot}")

    print("\n== 4. Reservando el turno ==")
    status, resp = call(
        "POST", "/appointments/",
        {"doctor": doctor_id, "start_datetime": slot["start_datetime"], "notes": "Turno de prueba"},
        token=token,
    )
    print(status, resp)
    if status != 201:
        print("La reserva falló.")
        sys.exit(1)

    print("\n== 5. Confirmando en 'Mis citas' ==")
    status, resp = call("GET", "/appointments/mine/", token=token)
    print(status, resp)

    print("\n== 6. Intentando reservar el MISMO horario de nuevo (debe fallar) ==")
    status, resp = call(
        "POST", "/appointments/",
        {"doctor": doctor_id, "start_datetime": slot["start_datetime"], "notes": "Intento de doble reserva"},
        token=token,
    )
    print(status, resp)
    if status == 400:
        print("\n✅ Correcto: el sistema rechazó la doble reserva, como se esperaba.")
    else:
        print("\n⚠️ Atención: se esperaba un error 400 y no ocurrió.")


if __name__ == "__main__":
    main()
