import re
from decimal import Decimal
from .domain import BusinessError


def parse_price(text):
    text = re.sub(r"[ \u00a0\u202f]+", "", text.casefold())
    match = re.fullmatch(
        r"(?:цена[=:]?)?(\d+(?:[.,]\d{1,2})?)(?:(млн|миллиона|миллионов|тыс|тысяч)\.?)?(?:₽|руб\.?|рублей)?(?:сндс)?",
        text,
    )
    if not match:
        raise BusinessError(
            "Укажите цену за одну единицу в рублях с НДС: 2730000 или 2,73 млн. Без валютного пересчёта."
        )
    value = Decimal(match[1].replace(",", "."))
    value *= 1000000 if match[2] in {"млн", "миллиона", "миллионов"} else 1000 if match[2] else 1
    if not 0 < value <= Decimal("999999999999.99"):
        raise BusinessError("Цена должна быть положительной и не превышать 999999999999,99 руб.")
    return value
