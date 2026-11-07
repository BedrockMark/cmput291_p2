"""Unit tests for pure helpers (no MongoDB server needed).

Run from the repo root:  python3 -m unittest discover tests
"""

import importlib.util
import re
import unittest
from datetime import date
from pathlib import Path

from wsapp import db, ui, validation


def load_loader_module():
    """Import load-json.py (its hyphenated name cannot be imported normally)."""
    path = Path(__file__).resolve().parent.parent / "load-json.py"
    spec = importlib.util.spec_from_file_location("load_json", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParseIntTests(unittest.TestCase):
    def test_accepts_integers_with_whitespace(self):
        self.assertEqual(validation.parse_positive_int(" 3 "), 3)

    def test_rejects_decimal_and_garbage(self):
        for text in ("2.5", "1e3", "abc", "", "3 seats", "٣"):
            with self.assertRaises(ValueError, msg=text):
                validation.parse_positive_int(text)

    def test_rejects_zero_and_negative(self):
        for text in ("0", "-1"):
            with self.assertRaises(ValueError):
                validation.parse_positive_int(text)

    def test_top_n_range(self):
        self.assertEqual(validation.parse_top_n("1"), 1)
        self.assertEqual(validation.parse_top_n("20"), 20)
        for text in ("0", "21"):
            with self.assertRaises(ValueError):
                validation.parse_top_n(text)

    def test_rating_range(self):
        self.assertEqual(validation.parse_rating("5"), 5)
        for text in ("0", "6", "4.5"):
            with self.assertRaises(ValueError):
                validation.parse_rating(text)


class ParseDateTests(unittest.TestCase):
    def test_valid_and_leap_day(self):
        self.assertEqual(validation.parse_date("2026-11-01"), date(2026, 11, 1))
        self.assertEqual(validation.parse_date("2028-02-29"), date(2028, 2, 29))

    def test_invalid_dates(self):
        for text in ("2027-02-29", "2026-04-31", "2026-13-01", "2026-1-05",
                     "2026/11/01", "20261101", "2026-11-01T00:00:00Z"):
            with self.assertRaises(ValueError, msg=text):
                validation.parse_date(text)


class ParseTextTests(unittest.TestCase):
    def test_trims_and_limits(self):
        self.assertEqual(validation.parse_reviewer("  Ann  "), "Ann")
        self.assertEqual(len(validation.parse_reviewer("x" * 80)), 80)
        with self.assertRaises(ValueError):
            validation.parse_reviewer("x" * 81)
        with self.assertRaises(ValueError):
            validation.parse_comment("   ")
        self.assertEqual(len(validation.parse_comment("y" * 500)), 500)
        with self.assertRaises(ValueError):
            validation.parse_comment("y" * 501)

    def test_category(self):
        self.assertEqual(validation.parse_category("  Computing "), "computing")
        self.assertIsNone(validation.parse_category("   "))


class FormatTests(unittest.TestCase):
    def test_price(self):
        self.assertEqual(ui.fmt_price(1500), "$15.00")
        self.assertEqual(ui.fmt_price(0), "$0.00")
        self.assertEqual(ui.fmt_price(5), "$0.05")
        self.assertEqual(ui.fmt_price(123456), "$1234.56")

    def test_average(self):
        self.assertEqual(ui.fmt_average(4.666666), "4.67")
        self.assertEqual(ui.fmt_average(4), "4.00")


class DbHelperTests(unittest.TestCase):
    def test_day_bounds(self):
        self.assertEqual(db.utc_day_bounds(date(2026, 10, 31)),
                         ("2026-10-31T00:00:00Z", "2026-11-01T00:00:00Z"))
        self.assertEqual(db.utc_day_bounds(date(2028, 2, 28)),
                         ("2028-02-28T00:00:00Z", "2028-02-29T00:00:00Z"))
        self.assertEqual(db.utc_day_bounds(date(2026, 12, 31))[1],
                         "2027-01-01T00:00:00Z")

    def test_literal_regex_is_literal(self):
        # Python's re and MongoDB's PCRE agree on these escapes.
        def matches(keyword, text):
            return re.search(db.literal_regex(keyword)["$regex"], text, re.I) is not None

        self.assertTrue(matches("C++", "Intro to C++"))
        self.assertTrue(matches("tech", "biotechnology"))
        self.assertTrue(matches("tech", "Technology"))
        self.assertFalse(matches("a.b", "axb"))
        self.assertTrue(matches("a.b", "a.b"))

    def test_exact_regex_matches_whole_value(self):
        pattern = db.exact_ci_regex("St. Albert")["$regex"]
        self.assertIsNotNone(re.search(pattern, "st. albert", re.I))
        self.assertIsNone(re.search(pattern, "StX Albert", re.I))
        self.assertIsNone(re.search(db.exact_ci_regex("Edmon")["$regex"], "Edmonton", re.I))

    def test_now_format(self):
        self.assertRegex(db.now_utc_str(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_active_filter(self):
        self.assertEqual(db.active_filter(_id="W1"), {"status": "active", "_id": "W1"})


class IterBatchesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = load_loader_module()

    def test_batches_and_blank_lines(self):
        lines = ['{"_id": "a"}\n', "\n", "   \n", '{"_id": "b"}\n', '{"_id": "c"}\n']
        batches = list(self.loader.iter_batches(lines, batch_size=2))
        self.assertEqual(batches, [
            (1, 4, [{"_id": "a"}, {"_id": "b"}]),
            (5, 5, [{"_id": "c"}]),
        ])

    def test_empty_input(self):
        self.assertEqual(list(self.loader.iter_batches(["\n", ""])), [])

    def test_malformed_line_reports_line_number(self):
        lines = ['{"_id": "a"}\n', "\n", '{"_id": \n']
        with self.assertRaisesRegex(self.loader.LoadError, "line 3"):
            list(self.loader.iter_batches(lines))

    def test_non_object_rejected(self):
        with self.assertRaisesRegex(self.loader.LoadError, "Line 1"):
            list(self.loader.iter_batches(["[1, 2]\n"]))


if __name__ == "__main__":
    unittest.main()
