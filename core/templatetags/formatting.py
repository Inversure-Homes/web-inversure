from django import template

register = template.Library()


@register.filter
def es_number(value, decimals=2):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ""
    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2
    fmt = f"{{:,.{decimals}f}}".format(num)
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")
