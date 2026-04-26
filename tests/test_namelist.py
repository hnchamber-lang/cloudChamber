import unittest
from datetime import datetime
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from build_project import _parse_dt

class TestNamelistValidation(unittest.TestCase):
    def test_parse_dt(self):
        self.assertEqual(_parse_dt("2026-04-21"), datetime(2026, 4, 21, 0, 0, 0))
        self.assertEqual(_parse_dt("2026-04-21", end=True), datetime(2026, 4, 21, 23, 59, 59))
        self.assertEqual(_parse_dt("2026-04-21 15:30:00"), datetime(2026, 4, 21, 15, 30, 0))
        
    def test_invalid_dt(self):
        with self.assertRaises(ValueError):
            _parse_dt("bad date")

if __name__ == "__main__":
    unittest.main()
