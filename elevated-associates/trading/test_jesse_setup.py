"""Guards the Jesse research setup: paper and backtests only, no keys, no paid live plugin."""
import re
import subprocess
import unittest
from pathlib import Path

JESSE = Path(__file__).parent / "jesse"
SETUP = (JESSE / "setup.sh").read_text()
CODE = "\n".join(line for line in SETUP.splitlines() if not line.lstrip().startswith("#"))


class JesseSetupTests(unittest.TestCase):
    def test_script_is_valid_bash(self):
        subprocess.run(["bash", "-n", str(JESSE / "setup.sh")], check=True)

    def test_never_installs_live_plugin(self):
        self.assertNotIn("install-live", CODE)

    def test_no_exchange_or_license_keys(self):
        self.assertIsNone(re.search(r"LICENSE_API_TOKEN|API_KEY|API_SECRET", CODE))

    def test_env_file_is_private_and_not_committed(self):
        self.assertIn("chmod 600", CODE)
        self.assertFalse(list(JESSE.glob(".env*")))

    def test_setup_is_idempotent_guarded(self):
        for guard in ('[ -d "$VENV" ]', '[ ! -f "$PROJECT/.env" ]', "SELECT 1 FROM pg_roles"):
            self.assertIn(guard, CODE)


if __name__ == "__main__":
    unittest.main()
