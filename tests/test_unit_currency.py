import pytest

from app.currency import convert_price


def test_convert_price_same_currency():
    rates = {"RUB": 1.0, "USD": 0.01, "EUR": 0.009}
    assert convert_price(123.45, "USD", "USD", rates) == 123.45


def test_convert_price_rub_to_usd():
    rates = {"RUB": 1.0, "USD": 0.01, "EUR": 0.009}
    assert convert_price(1000.0, "RUB", "USD", rates) == 10.0


def test_convert_price_usd_to_eur():
    rates = {"RUB": 1.0, "USD": 0.01, "EUR": 0.009}
    assert convert_price(10.0, "USD", "EUR", rates) == 9.0
