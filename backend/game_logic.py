import random
from decimal import Decimal

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

MIN_BET = Decimal("1.00")
MAX_BET = Decimal("1000.00")


def spin_wheel() -> int:
    """Generate a random roulette result (0-36)."""
    return random.randint(0, 36)


def get_color(number: int) -> str:
    if number == 0:
        return "green"
    return "red" if number in RED_NUMBERS else "black"


def calculate_win(bet_type: str, bet_value: str, result: int, amount: Decimal) -> Decimal:
    result_color = get_color(result)

    if bet_type == "number":
        try:
            num = int(bet_value)
        except ValueError:
            return Decimal("0")
        if num == result:
            return amount * 35
        return Decimal("0")

    elif bet_type == "color":
        # value: "red" or "black"
        if result == 0:
            return Decimal("0")
        if bet_value.lower() == result_color:
            return amount * 1
        return Decimal("0")

    elif bet_type == "parity":
        # value: "even" or "odd"
        if result == 0:
            return Decimal("0")
        is_even = result % 2 == 0
        if (bet_value.lower() == "even" and is_even) or (bet_value.lower() == "odd" and not is_even):
            return amount * 1
        return Decimal("0")

    elif bet_type == "dozen":
        # value: "1" (1-12), "2" (13-24), "3" (25-36)
        try:
            dozen = int(bet_value)
        except ValueError:
            return Decimal("0")
        ranges = {1: range(1, 13), 2: range(13, 25), 3: range(25, 37)}
        if dozen in ranges and result in ranges[dozen]:
            return amount * 2
        return Decimal("0")

    elif bet_type == "half":
        # value: "1" (1-18), "2" (19-36)
        try:
            half = int(bet_value)
        except ValueError:
            return Decimal("0")
        if result == 0:
            return Decimal("0")
        if half == 1 and 1 <= result <= 18:
            return amount * 1
        if half == 2 and 19 <= result <= 36:
            return amount * 1
        return Decimal("0")

    elif bet_type == "column":
        # value: "1", "2", "3" — columns of the roulette grid
        try:
            col = int(bet_value)
        except ValueError:
            return Decimal("0")
        # Column 1: 1,4,7,10,13,16,19,22,25,28,31,34
        # Column 2: 2,5,8,11,14,17,20,23,26,29,32,35
        # Column 3: 3,6,9,12,15,18,21,24,27,30,33,36
        if result == 0:
            return Decimal("0")
        if result % 3 == (col % 3):
            return amount * 2
        return Decimal("0")

    return Decimal("0")
