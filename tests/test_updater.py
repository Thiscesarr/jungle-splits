import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import updater

INSTALLER = b"MZ fake installer bytes"
SUMS = f"{hashlib.sha256(INSTALLER).hexdigest()}  JungleSplits-Setup.exe\nabc  JungleSplits-Portable.zip\n"


def fake_github(tag="v1.2.0", installer=INSTALLER, sums=SUMS, **release):
    files = {
        updater.LATEST_RELEASE_API: json.dumps({
            "tag_name": tag, "html_url": "https://example/release", **release,
            "assets": [{"name": "JungleSplits-Setup.exe", "browser_download_url": "https://dl/setup"},
                       {"name": "SHA256SUMS.txt", "browser_download_url": "https://dl/sums"}],
        }).encode(),
        "https://dl/setup": installer,
        "https://dl/sums": sums.encode(),
    }

    def fetch(url, timeout=0):
        if url not in files:
            raise OSError(url)
        return files[url]

    return fetch


class UpdaterTest(unittest.TestCase):
    def test_versions_compare_numerically(self):
        self.assertGreater(updater.version_tuple("v1.0.10"), updater.version_tuple("1.0.9"))
        self.assertEqual(updater.version_tuple("garbage"), (0,))

    def test_newer_release_is_offered(self):
        update = updater.check_latest("1.0.2", fetch=fake_github())
        self.assertEqual(update.version, "1.2.0")
        self.assertEqual(update.setup_url, "https://dl/setup")

    def test_same_older_or_unfinished_releases_are_not(self):
        self.assertIsNone(updater.check_latest("1.2.0", fetch=fake_github()))
        self.assertIsNone(updater.check_latest("1.3.0", fetch=fake_github()))
        self.assertIsNone(updater.check_latest("1.0.0", fetch=fake_github(draft=True)))
        self.assertIsNone(updater.check_latest("1.0.0", fetch=fake_github(prerelease=True)))

    def test_offline_means_no_update(self):
        def offline(url, timeout=0):
            raise OSError("no network")
        self.assertIsNone(updater.check_latest("1.0.0", fetch=offline))

    def test_download_checks_the_installer_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            update = updater.check_latest("1.0.0", fetch=fake_github())
            path = updater.download(update, Path(tmp), fetch=fake_github())
            self.assertEqual(path.read_bytes(), INSTALLER)
            tampered = fake_github(installer=b"something else")
            with self.assertRaises(ValueError):
                updater.download(update, Path(tmp) / "x", fetch=tampered)
            self.assertFalse((Path(tmp) / "x").exists())


if __name__ == "__main__":
    unittest.main()
