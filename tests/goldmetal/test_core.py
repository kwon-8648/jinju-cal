import unittest
from decimal import Decimal

from core import (
    RATE_ITEMS,
    build_rows,
    calculate_row,
    calculate_unit_price,
    parse_koreagoldx_prices,
)


class CoreTests(unittest.TestCase):
    def test_gold_reference_values(self):
        self.assertEqual(calculate_unit_price(375000, "GOLD", Decimal("1.0000")), 100000)
        self.assertEqual(calculate_unit_price(375000, "GOLD", Decimal("0.9940")), 99400)
        self.assertEqual(calculate_unit_price(375000, "GOLD", Decimal("0.7000")), 70000)
        self.assertEqual(calculate_unit_price(375000, "GOLD", Decimal("0.5100")), 51000)

    def test_original_total_967600(self):
        weights = {}
        for i, item in enumerate(RATE_ITEMS[:12]):
            key = f"{i:02d}:{item.metal_type}:{item.item_name}"
            weights[key] = {"input_weight": "1", "deduction_weight": "0"}
        rows = build_rows({"GOLD": 375000, "SILVER": 0, "PLATINUM": 0}, weights)
        total = sum(r["customer_price"] for r in rows)
        self.assertEqual(total, 967600)

    def test_deduction(self):
        d, c = calculate_row(100000, "10", "0.5")
        self.assertEqual(d, 50000)
        self.assertEqual(c, 950000)

    def test_api_parser_officialprice4_p_is_customer_sell(self):
        payload = {
            "officialPrice4": [{
                "s_pure": "900,000", "p_pure": "810,000",
                "s_silver": "12,000", "p_silver": "9,000",
                "s_white": "450,000", "p_white": "390,000",
            }]
        }
        prices, details = parse_koreagoldx_prices(payload)
        self.assertEqual(prices["GOLD"], 810000)
        self.assertEqual(prices["SILVER"], 9000)
        self.assertEqual(prices["PLATINUM"], 390000)
        self.assertEqual(details["metals"]["PLATINUM"]["alias"], "white")

    def test_api_parser_auto_swaps_if_field_direction_changes(self):
        payload = {
            "officialPrice4": {
                "s_pure": "810000", "p_pure": "900000",
                "s_silver": "9000", "p_silver": "12000",
                "s_white": "390000", "p_white": "450000",
            }
        }
        prices, _ = parse_koreagoldx_prices(payload)
        self.assertEqual(prices, {"GOLD": 810000, "SILVER": 9000, "PLATINUM": 390000})


if __name__ == "__main__":
    unittest.main()
