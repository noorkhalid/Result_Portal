from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    try:
        return d.get(key, "")
    except Exception:
        return ""


@register.filter
def ordinal(value):
    """Convert an int to 1st/2nd/3rd/4th... (English ordinal)."""
    try:
        n = int(value)
    except Exception:
        return value

    # 11th, 12th, 13th ... 20th
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    return f"{n}{suffix}"
