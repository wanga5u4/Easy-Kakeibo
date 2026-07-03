from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


DEFAULT_BASE_CURRENCY = "JPY"
ENABLED_CURRENCY_CODES = ("JPY", "CNY")
MAX_AMOUNT = Decimal("999999999999")
MAX_MINOR_UNITS = 10**15
MAX_EXCHANGE_RATE_LENGTH = 24
MAX_EXCHANGE_RATE_DECIMAL_PLACES = 12

CURRENCIES = {
    "JPY": {
        "code": "JPY",
        "decimal_places": 0,
        "symbol": "¥",
    },
    "CNY": {
        "code": "CNY",
        "decimal_places": 2,
        "symbol": "¥",
    },
    "USD": {
        "code": "USD",
        "decimal_places": 2,
        "symbol": "$",
    },
    "EUR": {
        "code": "EUR",
        "decimal_places": 2,
        "symbol": "€",
    },
    "KRW": {
        "code": "KRW",
        "decimal_places": 0,
        "symbol": "₩",
    },
}

DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class CurrencyValidationError(ValueError):
    pass


def validate_currency_code(code, enabled_only=False):
    normalized = (code or "").strip().upper()
    allowed_codes = ENABLED_CURRENCY_CODES if enabled_only else CURRENCIES.keys()
    if normalized not in allowed_codes:
        raise CurrencyValidationError("invalid currency code")
    return normalized


def get_currency_decimal_places(code):
    return CURRENCIES[validate_currency_code(code)]["decimal_places"]


def get_currency_symbol(code):
    return CURRENCIES[validate_currency_code(code)]["symbol"]


def parse_plain_decimal(value, max_length=32):
    text = str(value).strip()
    if not text or len(text) > max_length:
        raise CurrencyValidationError("invalid decimal")
    if "e" in text.lower() or not DECIMAL_RE.match(text):
        raise CurrencyValidationError("invalid decimal")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise CurrencyValidationError("invalid decimal") from exc
    if not amount.is_finite():
        raise CurrencyValidationError("invalid decimal")
    return amount


def amount_to_minor_units(value, currency_code):
    currency_code = validate_currency_code(currency_code)
    amount = parse_plain_decimal(value)
    decimal_places = get_currency_decimal_places(currency_code)
    exponent = Decimal(1).scaleb(-decimal_places)
    quantized = amount.quantize(exponent, rounding=ROUND_HALF_UP)
    if amount != quantized:
        raise CurrencyValidationError("too many decimal places")
    if amount <= 0 or amount > MAX_AMOUNT:
        raise CurrencyValidationError("amount out of range")
    minor_units = int(quantized * (10**decimal_places))
    if minor_units <= 0 or minor_units > MAX_MINOR_UNITS:
        raise CurrencyValidationError("amount out of range")
    return minor_units


def amount_to_minor_units_rounded(value, currency_code):
    currency_code = validate_currency_code(currency_code)
    amount = Decimal(str(value))
    decimal_places = get_currency_decimal_places(currency_code)
    exponent = Decimal(1).scaleb(-decimal_places)
    quantized = amount.quantize(exponent, rounding=ROUND_HALF_UP)
    if quantized <= 0:
        quantized = exponent
    minor_units = int(quantized * (10**decimal_places))
    return max(minor_units, 1)


def minor_units_to_decimal(minor_units, currency_code):
    decimal_places = get_currency_decimal_places(currency_code)
    return Decimal(int(minor_units)) / Decimal(10**decimal_places)


def decimal_to_api_number(value):
    value = Decimal(value)
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def minor_units_to_api_number(minor_units, currency_code):
    return decimal_to_api_number(minor_units_to_decimal(minor_units, currency_code))


def validate_exchange_rate(value):
    rate = parse_plain_decimal(value, max_length=MAX_EXCHANGE_RATE_LENGTH)
    if rate <= 0:
        raise CurrencyValidationError("exchange rate must be positive")
    sign, digits, exponent = rate.as_tuple()
    if len(digits) > 18:
        raise CurrencyValidationError("exchange rate too long")
    if exponent < -MAX_EXCHANGE_RATE_DECIMAL_PLACES:
        raise CurrencyValidationError("exchange rate too precise")
    return rate


def decimal_to_plain_string(value):
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def convert_amount(original_amount_minor, currency_code, exchange_rate, base_currency_code):
    currency_code = validate_currency_code(currency_code)
    base_currency_code = validate_currency_code(base_currency_code)
    rate = validate_exchange_rate(exchange_rate)
    original_amount = minor_units_to_decimal(original_amount_minor, currency_code)
    converted = original_amount * rate
    base_places = get_currency_decimal_places(base_currency_code)
    exponent = Decimal(1).scaleb(-base_places)
    quantized = converted.quantize(exponent, rounding=ROUND_HALF_UP)
    minor_units = int(quantized * (10**base_places))
    if minor_units <= 0 or minor_units > MAX_MINOR_UNITS:
        raise CurrencyValidationError("converted amount out of range")
    return minor_units


def invert_exchange_rate(exchange_rate):
    rate = validate_exchange_rate(exchange_rate)
    inverted = Decimal("1") / rate
    quantized = inverted.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)
    return validate_exchange_rate(decimal_to_plain_string(quantized))


def format_money(value, currency_code):
    currency_code = validate_currency_code(currency_code)
    amount = Decimal(value)
    decimal_places = get_currency_decimal_places(currency_code)
    exponent = Decimal(1).scaleb(-decimal_places)
    quantized = amount.quantize(exponent, rounding=ROUND_HALF_UP)
    formatted = f"{quantized:,.{decimal_places}f}"
    return f"{get_currency_symbol(currency_code)}{formatted} {currency_code}"


def format_money_minor(minor_units, currency_code):
    return format_money(minor_units_to_decimal(minor_units, currency_code), currency_code)


def currency_config_for_client():
    return {
        code: {
            "code": code,
            "decimal_places": CURRENCIES[code]["decimal_places"],
            "symbol": CURRENCIES[code]["symbol"],
        }
        for code in ENABLED_CURRENCY_CODES
    }
