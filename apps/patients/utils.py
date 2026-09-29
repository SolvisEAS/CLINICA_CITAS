import re


def normalize_document_number(value):
    """
    Deja solo los dígitos de un número de documento: saca puntos,
    comas, espacios y guiones (ej. "1.234.567-8" -> "12345678"),
    tal como pide el negocio ("cédula sin puntos ni comas").
    """
    return re.sub(r"\D", "", value or "")
