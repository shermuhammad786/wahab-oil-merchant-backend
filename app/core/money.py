from decimal import Decimal, ROUND_HALF_UP


ZERO_MONEY = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")


def to_decimal(value: object) -> Decimal:
    if value is None:
        return ZERO_MONEY
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: object) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
