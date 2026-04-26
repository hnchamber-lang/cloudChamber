import unittest
from datetime import datetime
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from build_project import _parse_date_from

class TestParseDate(unittest.TestCase):
    def test_known_formats(self):
        self.assertEqual(_parse_date_from("20260421", ""), datetime(2026, 4, 21))
        self.assertEqual(_parse_date_from("2026-04-21", ""), datetime(2026, 4, 21))
        self.assertEqual(_parse_date_from("2026_04_21", ""), datetime(2026, 4, 21))
        self.assertEqual(_parse_date_from("20260421153000", ""), datetime(2026, 4, 21, 15, 30, 0))
        self.assertEqual(_parse_date_from("2026-04-21 153000", ""), datetime(2026, 4, 21, 15, 30, 0))
    
    def test_custom_format(self):
        self.assertEqual(_parse_date_from("26-04-21", "%y-%m-%d"), datetime(2026, 4, 21))
        
    def test_invalid_date(self):
        self.assertIsNone(_parse_date_from("not-a-date", ""))
        self.assertIsNone(_parse_date_from("2026-13-45", ""))
        
if __name__ == "__main__":
    unittest.main()
