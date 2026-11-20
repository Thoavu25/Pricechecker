from decimal import Decimal
from typing import Protocol


class PriceLabelStrategy(Protocol):
    def label(self, price: Decimal, reference_price: Decimal) -> str: ...


class RelativePriceLabelStrategy:
    def label(self, price: Decimal, reference_price: Decimal) -> str:
        ratio = price / reference_price
        if ratio <= Decimal("0.80"):
            return "Very inexpensive"
        if ratio <= Decimal("0.95"):
            return "Inexpensive"
        if ratio <= Decimal("1.05"):
            return "Similar price"
        if ratio <= Decimal("1.20"):
            return "Expensive"
        return "Very expensive"

#weekend