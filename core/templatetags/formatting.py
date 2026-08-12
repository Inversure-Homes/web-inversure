from django import template

register = template.Library()


@register.filter
def es_number(value, decimals=2):
    try:
        if isinstance(value, str):
            s = value.strip().replace("€", "").replace("%", "").strip()
            if not s:
                return ""
            if "." in s and "," in s:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", ".")
            num = float(s)
        else:
            num = float(value)
    except (TypeError, ValueError):
        return ""
    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2
    fmt = f"{{:,.{decimals}f}}".format(num)
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


@register.filter
def fecha_larga(value):
    """
    «23 de junio de 2026». En un contrato la fecha se escribe así.

    No se usa el filtro `date` de Django con formato porque depende del idioma
    activo, y un contrato no puede salir en inglés porque alguien haya cambiado
    una configuración.
    """
    if not value:
        return ""
    try:
        return "{} de {} de {}".format(value.day, MESES_ES[value.month - 1], value.year)
    except (AttributeError, IndexError, TypeError):
        return ""
