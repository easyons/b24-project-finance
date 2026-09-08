"""Финансовые расчёты по проекту. Чистые функции без базы данных —
их можно проверить тестами, не поднимая приложение.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

INCOME = "income"
EXPENSE = "expense"


@dataclass(frozen=True)
class Summary:
    """Экономика одного проекта. Суммы — в копейках."""

    income: int
    expense: int

    @property
    def profit(self) -> int:
        return self.income - self.expense

    @property
    def margin(self) -> Decimal | None:
        """Рентабельность в процентах: прибыль к доходам.

        Если доходов ещё нет, рентабельность не определена — возвращаем None,
        а не ноль. Ноль означал бы «сработали в ноль», а это не так:
        проект с расходами и без выручки убыточен, просто база для процента
        отсутствует.
        """
        if self.income == 0:
            return None
        ratio = Decimal(self.profit) / Decimal(self.income) * 100
        return ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def summarize(entries) -> Summary:
    """Считает доходы и расходы по списку операций.

    Каждая операция — объект с полями .amount (копейки) и .kind
    ('income' или 'expense').
    """
    income = sum(e.amount for e in entries if e.kind == INCOME)
    expense = sum(e.amount for e in entries if e.kind == EXPENSE)
    return Summary(income=income, expense=expense)


def by_article(entries) -> dict[str, int]:
    """Разрез «сколько по каждой статье» — для карточки проекта."""
    totals: dict[str, int] = {}
    for entry in entries:
        totals[entry.article_name] = totals.get(entry.article_name, 0) + entry.amount
    return totals
