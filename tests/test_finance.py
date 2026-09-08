"""Проверки экономики проекта: прибыль, рентабельность, краевые случаи."""
from dataclasses import dataclass
from decimal import Decimal

from app.finance import EXPENSE, INCOME, by_article, summarize


@dataclass
class FakeEntry:
    """Заменяет строку базы: расчётам нужны только сумма, тип и статья."""
    amount: int
    kind: str
    article_name: str = "статья"


def test_profit_and_margin():
    entries = [
        FakeEntry(20000000, INCOME),   # 200 000 ₽
        FakeEntry(5000000, EXPENSE),   # 50 000 ₽
        FakeEntry(3000000, EXPENSE),   # 30 000 ₽
    ]
    summary = summarize(entries)
    assert summary.income == 20000000
    assert summary.expense == 8000000
    assert summary.profit == 12000000
    assert summary.margin == Decimal("60.0")


def test_margin_is_undefined_without_income():
    """Расходы есть, выручки нет — процент считать не от чего."""
    summary = summarize([FakeEntry(500000, EXPENSE)])
    assert summary.profit == -500000
    assert summary.margin is None


def test_margin_can_be_negative():
    summary = summarize([FakeEntry(10000, INCOME), FakeEntry(15000, EXPENSE)])
    assert summary.margin == Decimal("-50.0")


def test_empty_project():
    summary = summarize([])
    assert (summary.income, summary.expense, summary.profit) == (0, 0, 0)
    assert summary.margin is None


def test_margin_rounds_to_one_decimal():
    # 10000 дохода, 6667 расхода -> 33.33% -> округляем до 33.3
    summary = summarize([FakeEntry(10000, INCOME), FakeEntry(6667, EXPENSE)])
    assert summary.margin == Decimal("33.3")


def test_by_article_groups_repeated_names():
    entries = [
        FakeEntry(1000, EXPENSE, "Расходы на ИИ"),
        FakeEntry(2500, EXPENSE, "Расходы на ИИ"),
        FakeEntry(700, EXPENSE, "Аренда сервера"),
    ]
    assert by_article(entries) == {"Расходы на ИИ": 3500, "Аренда сервера": 700}
