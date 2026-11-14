import json
import tempfile
import unittest
from pathlib import Path

from cryptomon import app


class Logic(unittest.TestCase):
    def test_formatting(self):
        self.assertEqual(app.fmt_amount(0.25), "0.25")
        self.assertEqual(app.fmt_amount(5200), "5,200.00")
        self.assertEqual(app.fmt_amount(0), "0")
        self.assertEqual(app.fmt_price(50868.4), "50,868")
        self.assertEqual(app.fmt_price(0.0912), "0.0912")
        self.assertEqual(app.fmt_price(0.00001234), "0.00001234")
        self.assertEqual(app.fmt_money(-12.5, "gbp"), "-£12.50")
        self.assertEqual(app.fmt_money(12.5, "usd", True), "+$12.50")
        self.assertEqual(app.fmt_pct(None), "-")

    def test_portfolio(self):
        hold = [{"id": "a", "amount": 2}, {"id": "b", "amount": 1}, {"id": "x", "amount": 9}]
        data = {"a": {"price": 110.0, "change": 10.0}, "b": {"price": 50.0, "change": None}}
        total, delta, pct = app.portfolio(hold, data)  # unpriced "x" is ignored
        self.assertAlmostEqual(total, 270.0)
        self.assertAlmostEqual(delta, 20.0)
        self.assertAlmostEqual(pct, 20 / 250 * 100)
        self.assertEqual(app.portfolio([], {})[2], None)

    def test_config_roundtrip_and_hostile_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c" / "config.json"
            cfg = app.load_config(p)
            self.assertEqual(cfg["holdings"], [])
            cfg["holdings"].append({"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "amount": 1.5})
            app.save_config(cfg, p)
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            self.assertEqual(app.load_config(p)["holdings"][0]["amount"], 1.5)
            p.write_text(json.dumps({"currency": "doge", "opacity": 999, "holdings": [
                {"id": "a", "amount": "x"}, {"id": "b", "amount": -1}, {"amount": 1},
                {"id": "c", "amount": 2}, {"id": "c", "amount": 3}, 7, None]}))
            c = app.load_config(p)
            self.assertEqual(c["currency"], "gbp")
            self.assertEqual(c["opacity"], 130)
            self.assertEqual([h["id"] for h in c["holdings"]], ["c"])
            p.write_text("not json")
            self.assertEqual(app.load_config(p)["holdings"], [])


if __name__ == "__main__":
    unittest.main()
