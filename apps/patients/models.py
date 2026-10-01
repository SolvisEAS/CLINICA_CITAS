from django.core.validators import RegexValidator
from django.db import models

DOCUMENT_NUMBER_VALIDATOR = RegexValidator(
    regex=r"^\d+$",
    message="El número de documento debe tener solo dígitos, sin puntos ni comas.",
)


class Patient(models.Model):
    """
    Paciente sin cuenta ni login (decisión de negocio: el paciente no
    se registra ni inicia sesión). Se identifica con su número de
    documento (cédula, sin puntos ni comas) — que además es la clave
    primaria del modelo — junto con nombre, teléfono y correo. Con
    esos cuatro datos alcanza para reservar; con la cédula puede
    después volver a consultar, editar o cancelar su cita.
    """

    document_number = models.CharField(
        "Número de documento",
        max_length=20,
        primary_key=True,
        validators=[DOCUMENT_NUMBER_VALIDATOR],
        help_text="Cédula sin puntos ni comas.",
    )
    name = models.CharField("Nombre y apellido", max_length=200)
    phone = models.CharField("Teléfono", max_length=30)
    email = models.EmailField("Correo electrónico", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.document_number})"


class TreatmentRecord(models.Model):
    """
    Historial de tratamientos de un paciente. Lo carga el doctor (o un
    administrador) después de una consulta — el paciente no lo ve ni
    lo edita, ya que no tiene cuenta.
    """

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="treatment_records"
    )
    doctor = models.ForeignKey(
        "doctors.Doctor", on_delete=models.CASCADE, related_name="treatment_records"
    )
    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treatment_record",
    )
    reason = models.CharField("Motivo / tipo de consulta", max_length=200, blank=True)
    # Se muestra como "Observaciones"; se mantiene el nombre del campo
    # para no migrar los registros existentes.
    description = models.TextField("Observaciones")
    treatment = models.TextField("Tratamiento / indicaciones", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.patient} · {self.created_at:%d/%m/%Y}"
