"""The command-line tooling around the services: the .env reader shared by every tool, and first-run setup."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import envfile  # noqa: E402


class EnvFileTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text(text)
            return envfile.parse(p)

    def test_comments_quotes_export_and_last_assignment(self):
        env = self.parse(
            "# whole line\n\nA=1   # inline comment\nB=\" spaced # kept \"\nC='single # kept'\nexport D=4\nA=2\nE=\nF=x#not-a-comment\n"
        )
        self.assertEqual(env, {"A": "2", "B": " spaced # kept ", "C": "single # kept", "D": "4", "E": "", "F": "x#not-a-comment"})

    def test_missing_file_is_empty(self):
        self.assertEqual(envfile.parse("/nonexistent/.env"), {})

    def test_format_line_round_trips(self):
        for value in ("plain", "has space", "has # hash", "a=b", "mật-khẩu"):
            self.assertEqual(self.parse(envfile.format_line("K", value) + "\n")["K"], value)


class SetupTests(unittest.TestCase):
    def run_setup(self, root):
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "setup_env.py")],
            env=dict(os.environ, TRENDVN_SETUP_ROOT=str(root)),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_copying_the_example_env_still_gets_real_secrets(self):
        """`cp .env.example .env` is a natural first move: empty or commented secret lines must not be taken as 'already set'."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".env").write_text((ROOT / ".env.example").read_text())
            self.run_setup(root)
            env = envfile.parse(root / ".env")
            self.assertEqual(len(env["N8N_ENCRYPTION_KEY"]), 64)
            self.assertEqual(len(env["TRENDVN_TOKEN"]), 64)
            self.assertNotIn("#", env["TRENDVN_TOKEN"])
            self.assertEqual(oct((root / ".env").stat().st_mode & 0o777), "0o600")

    def test_empty_or_comment_only_secret_lines_are_treated_as_not_set(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".env").write_text("N8N_ENCRYPTION_KEY=     # generated later\nTRENDVN_TOKEN=\n")
            self.run_setup(root)
            env = envfile.parse(root / ".env")
            self.assertEqual((len(env["N8N_ENCRYPTION_KEY"]), len(env["TRENDVN_TOKEN"])), (64, 64))

    def test_setup_is_idempotent_and_never_overwrites_values_you_set(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".env").write_text("TRENDVN_TZ=Asia/Tokyo\nTRENDVN_TOKEN=" + "a" * 40 + "\n")
            self.run_setup(root)
            first = envfile.parse(root / ".env")
            self.assertEqual(first["TRENDVN_TOKEN"], "a" * 40)
            self.assertEqual(first["TRENDVN_TZ"], "Asia/Tokyo")
            self.run_setup(root)
            self.assertEqual(envfile.parse(root / ".env"), first)
            for sub in ("worker", "agent", "backups"):
                self.assertTrue((root / "data" / sub).is_dir())


class BackupProfilesTests(unittest.TestCase):
    """The TikTok sessions in a backup: every account's profile, without Chrome's caches and lock files."""

    def pack(self, profiles):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in profiles:
                for rel in (
                    "Default/Cookies",
                    "Cache/blob",
                    "Code Cache/js/x",
                    "GPUCache/y",
                    "Service Worker/CacheStorage/z",
                    "SingletonLock",
                    "SingletonSocket",
                ):
                    path = root / "profiles" / name / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("x")
            (root / "profiles" / "other").mkdir(parents=True)  # not an account profile: never packed
            out = root / "s.tgz"
            r = subprocess.run(
                ["bash", "-c", '. "$1"; pack_profiles "$2" "$3"', "x", str(ROOT / "scripts" / "lib.sh"), str(out), str(root / "profiles")],
                capture_output=True,
                text=True,
            )
            names = subprocess.run(["tar", "tzf", str(out)], capture_output=True, text=True).stdout.split() if out.exists() else []
            return r.returncode, names

    def test_every_account_profile_goes_in_with_its_session_and_nothing_that_chrome_rebuilds(self):
        code, names = self.pack(["publisher", "publisher-pets"])
        self.assertEqual(code, 0)
        self.assertIn("publisher/Default/Cookies", names)
        self.assertIn("publisher-pets/Default/Cookies", names)
        self.assertFalse([n for n in names if "Cache" in n or "Singleton" in n], names)
        self.assertFalse([n for n in names if n.startswith("other")], names)

    def test_no_profile_is_told_apart_from_a_failure(self):
        code, names = self.pack([])
        self.assertEqual((code, names), (10, []))  # "nothing to pack" is a warning for the caller, not an error

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read anything")
    def test_a_profile_that_cannot_be_read_fails_instead_of_passing_for_a_backup(self):
        """At HEAD `set -e` stopped the backup; a blanket `|| true` once let a 247-byte archive without cookies through."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cookies = root / "profiles" / "publisher" / "Default" / "Cookies"
            cookies.parent.mkdir(parents=True)
            cookies.write_text("secret")
            cookies.chmod(0)
            r = subprocess.run(
                ["bash", "-c", '. "$1"; pack_profiles "$2" "$3"', "x", str(ROOT / "scripts" / "lib.sh"), str(root / "s.tgz"), str(root / "profiles")],
                capture_output=True, text=True,
            )  # fmt: skip
        self.assertNotIn(r.returncode, (0, 10))

    def test_backup_stops_when_the_profiles_cannot_be_packed(self):
        script = (ROOT / "scripts" / "backup.sh").read_text()
        self.assertIn("pack_rc", script)
        self.assertNotIn('pack_profiles "$TMP/tiktok_session.tgz" data/agent/profiles || true', script)


if __name__ == "__main__":
    unittest.main()
