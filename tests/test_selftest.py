import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import selftest


class SelfTestTest(unittest.TestCase):
    def test_all_checks_pass_from_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.txt"
            code = selftest.main(report)
            self.assertEqual(code, 0, report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
