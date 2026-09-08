"""Проверки разбора и вывода сумм — здесь легче всего потерять копейки."""
import pytest

from app.money import AmountError, format_amount, parse_amount


@pytest.mark.parametrize("raw, cents", [
    ("100", 10000),
    ("100.50", 10050),
    ("100,50", 10050),
    ("1 234,56", 123456),
    ("0.01", 1),
    (1500, 150000),
])
def test_parse_amount(raw, cents):
    assert parse_amount(raw) == cents


@pytest.mark.parametrize("raw", ["", "   ", "abc", "-100", "0"])
def test_parse_amount_rejects_garbage(raw):
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_parse_amount_rounds_half_up():
    # Третий знак после запятой округляется к ближайшей копейке.
    assert parse_amount("10.005") == 1001
    assert parse_amount("10.004") == 1000


def test_no_float_drift():
    """Классическая ловушка float: 0.1 + 0.2. В копейках её нет."""
    assert parse_amount("0.1") + parse_amount("0.2") == parse_amount("0.3")


@pytest.mark.parametrize("cents, text", [
    (0, "0,00"),
    (123456, "1 234,56"),
    (100000000, "1 000 000,00"),
    (-50000, "−500,00"),
])
def test_format_amount(cents, text):
    assert format_amount(cents) == text
