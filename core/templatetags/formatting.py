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
