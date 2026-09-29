#!/usr/bin/env python3
"""
Script de prueba: simula lo que haría un paciente real contra la API
ya desplegada en el servidor. Solo usa la librería estándar de Python
(no hace falta instalar nada nuevo en el venv). El paciente NO necesita
cuenta ni login — solo su cédula y sus datos básicos.

Uso:
    python3 test_reserva.py <numero_de_documento>

Ejemplo:
    python3 test_reserva.py 12345678

Qué hace, paso a paso:
    1. Lista los doctores disponibles (endpoint público).
    2. Busca el primer día (de los próximos 14) en que ese doctor
       tenga al menos un horario libre.
    3. Reserva ese horario indicando los 4 datos del paciente.
    4. Confirma que la cita aparece al consultar por cédula.
    5. Intenta reservar el MISMO horario de nuevo con OTRA cédula, a
       propósito, para comprobar que el sistema lo rechaza (no permite
       doble reserva del mismo doctor).
    6. Intenta reservar OTRO horario ese mismo día con la MISMA
       cédula, a propósito, para comprobar el límite de un turno por
       día por paciente.
    7. Cancela la cita reservada en el paso 3.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://95.111.213.227:8001/api"


def call(method, path, data=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    if len(sys.argv) != 2:
        print("Uso: python3 test_reserva.py <numero_de_documento>")
        sys.exit(1)

    document_number = sys.argv[1]
    otro_documento = document_number + "9"  # cédula distinta, para el intento de doble reserva

    print("== 1. Lista de doctores (público, sin login) ==")
    status, resp = call("GET", "/doctors/")
    print(status, resp)
    doctores = resp.get("results", resp) if isinstance(resp, dict) else resp
    if not doctores:
        print("No hay ningún doctor cargado todavía. Cargá uno desde /admin/ y volvé a correr el script.")
        sys.exit(1)
    doctor_id = doctores[0]["id"]
    print(f"\nUsando doctor id={doctor_id}")

    print("\n== 2. Buscando el primer día con horarios libres (próximos 14 días) ==")
    slot = None
    slot_alternativo = None
    for i in range(1, 15):
        d = date.today() + timedelta(days=i)
        status, resp = call("GET", f"/doctors/{doctor_id}/availability/?date={d.isoformat()}")
        if status == 200 and resp:
            print(f"{d.isoformat()}: {len(resp)} horario(s) libres")
            slot = resp[0]
            if len(resp) > 1:
                slot_alternativo = resp[1]
            break
        else:
            print(f"{d.isoformat()}: sin horarios libres")
    if not slot:
        print("\nNo se encontró ningún horario libre en los próximos 14 días.")
        print("Revisá que el doctor tenga un 'Horario semanal' cargado en /admin/.")
        sys.exit(1)

    print(f"\nHorario elegido: {slot}")

    print("\n== 3. Reservando el turno (sin login, con los datos del paciente) ==")
    status, resp = call(
        "POST", "/appointments/",
        {
            "document_number": document_number,
            "name": "Paciente de Prueba",
            "phone": "099000000",
            "email": "paciente.prueba@example.com",
            "doctor": doctor_id,
            "start_datetime": slot["start_datetime"],
            "notes": "Turno de prueba",
        },
    )
    print(status, resp)
    if status != 201:
        print("La reserva falló.")
        sys.exit(1)
    appointment_id = resp["id"]

    print("\n== 4. Consultando mis turnos por cédula ==")
    status, resp = call("GET", f"/patients/{document_number}/appointments/")
    print(status, resp)

    print("\n== 5. Intentando reservar el MISMO horario con OTRA cédula (debe fallar) ==")
    status, resp = call(
        "POST", "/appointments/",
        {
            "document_number": otro_documento,
            "name": "Otro Paciente",
            "phone": "099111111",
            "email": "otro.paciente@example.com",
            "doctor": doctor_id,
            "start_datetime": slot["start_datetime"],
            "notes": "Intento de doble reserva",
        },
    )
    print(status, resp)
    if status == 400:
        print("✅ Correcto: el sistema rechazó la doble reserva del mismo horario.")
    else:
        print("⚠️ Atención: se esperaba un error 400 y no ocurrió.")

    if slot_alternativo:
        print("\n== 6. Intentando reservar OTRO horario el mismo día con la MISMA cédula (debe fallar) ==")
        status, resp = call(
            "POST", "/appointments/",
            {
                "document_number": document_number,
                "name": "Paciente de Prueba",
                "phone": "099000000",
                "email": "paciente.prueba@example.com",
                "doctor": doctor_id,
                "start_datetime": slot_alternativo["start_datetime"],
                "notes": "Segundo turno el mismo día",
            },
        )
        print(status, resp)
        if status == 400:
            print("✅ Correcto: el sistema rechazó el segundo turno el mismo día.")
        else:
            print("⚠️ Atención: se esperaba un error 400 y no ocurrió.")
    else:
        print("\n== 6. (Se salteó: el doctor solo tenía un horario libre ese día) ==")

    print("\n== 7. Cancelando el turno reservado en el paso 3 ==")
    status, resp = call("PATCH", f"/patients/{document_number}/appointments/{appointment_id}/cancel/", {})
    print(status, resp)


if __name__ == "__main__":
    main()
