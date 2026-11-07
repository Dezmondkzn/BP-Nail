from decimal import Decimal

import pytest

from bp_bot.domain import BusinessError
from bp_bot.pricing import parse_price


@pytest.mark.parametrize(
    "text,expected",
    [
        ("4,9 млн.", "4900000"),
        ("4.9 млн.", "4900000"),
        ("4,9 млн", "4900000"),
        ("4,9 МЛН. руб. с НДС", "4900000"),
        ("4\u202f900\u202f000 руб.", "4900000"),
        ("цена: 4,9 млн. ₽", "4900000"),
        ("4900 тыс.", "4900000"),
        ("4,91 тыс. руб.", "4910"),
        ("4.90 руб.", "4.90"),
    ],
)
def test_prices_with_common_abbreviation_punctuation(text, expected):
    assert parse_price(text) == Decimal(expected)


@pytest.mark.parametrize(
    "text", ["4,9 млн..", "4,9 млн. USD", "4,9 млн. без НДС", "-4,9 млн.", "0 млн.", "4,999 млн."]
)
def test_price_abbreviations_do_not_weaken_validation(text):
    with pytest.raises(BusinessError):
        parse_price(text)
