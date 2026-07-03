from decimal import Decimal

import pytest

from currency import (
    CurrencyValidationError,
    amount_to_minor_units,
    convert_amount,
    format_money,
    format_money_minor,
    minor_units_to_decimal,
    validate_currency_code,
    validate_exchange_rate,
)


def test_jpy_amount_to_minor_units():
    assert amount_to_minor_units("1000", "JPY") == 1000
    with pytest.raises(CurrencyValidationError):
        amount_to_minor_units("1000.50", "JPY")


def test_cny_amount_to_minor_units():
    assert amount_to_minor_units("100.50", "CNY") == 10050
    with pytest.raises(CurrencyValidationError):
        amount_to_minor_units("100.555", "CNY")


def test_minor_units_to_decimal_and_formatting():
    assert minor_units_to_decimal(1000, "JPY") == Decimal("1000")
    assert minor_units_to_decimal(10050, "CNY") == Decimal("100.50")
    assert format_money_minor(1000, "JPY") == "¥1,000 JPY"
    assert format_money("100.50", "CNY") == "¥100.50 CNY"


def test_decimal_exchange_rate_conversion_rounds_to_base_currency():
    assert convert_amount(1000, "JPY", "0.047", "CNY") == 4700
    assert convert_amount(10050, "CNY", "21.277", "JPY") == 2138


def test_invalid_currency_amount_and_exchange_rate():
    with pytest.raises(CurrencyValidationError):
        validate_currency_code("USD", enabled_only=True)
    for value in ["", "abc", "NaN", "Infinity", "-1", "1e-3", "0"]:
        with pytest.raises(CurrencyValidationError):
            validate_exchange_rate(value)
    for value in ["", "abc", "0", "-1", "1e3", "9999999999999"]:
        with pytest.raises(CurrencyValidationError):
            amount_to_minor_units(value, "CNY")
