"""Деньги в приложении хранятся в копейках — целыми числами.

Это осознанное решение: float для денег даёт ошибки округления
(0.1 + 0.2 != 0.3), а хранение целых копеек делает суммы точными.
Разбор строки и вывод идут через Decimal, поэтому «1 234,56» и
«1234.56» читаются одинаково.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("100")


class AmountError(ValueError):
    """Строку не удалось прочитать как сумму денег."""


def parse_amount(raw: str | float | int) -> int:
    """«1 234,56» -> 123456 копеек. Пустая строка и мусор дают AmountError."""
    if isinstance(raw, (int, float)):
        text = str(raw)
    else:
        text = (raw or "").strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not text:
        raise AmountError("Сумма не указана")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise AmountError(f"Не похоже на сумму: {raw!r}") from exc
    if value <= 0:
        raise AmountError("Сумма должна быть больше нуля")
    cents = (value * CENTS).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def to_rubles(cents: int) -> Decimal:
    """Копейки -> рубли как Decimal, для расчётов и шаблонов."""
    return (Decimal(cents) / CENTS).quantize(Decimal("0.01"))


def format_amount(cents: int) -> str:
    """123456 -> «1 234,56». Формат для показа человеку."""
    rubles = to_rubles(abs(cents))
    whole, _, frac = f"{rubles:.2f}".partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    sign = "−" if cents < 0 else ""
    return f"{sign}{' '.join(groups)},{frac}"


def format_percent(value) -> str:
    """Рентабельность для показа: «49,9 %» или прочерк, если считать не от чего."""
    if value is None:
        return "—"
    return f"{value}".replace(".", ",") + " %"
