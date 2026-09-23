import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "skills" / "goal-alignment-guard" / "scripts" / "global_anchor.py"
spec = importlib.util.spec_from_file_location("global_anchor", MODULE)
anchor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(anchor)


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "codex-config"
        self.home.mkdir()
        self.target = self.home / "AGENTS.md"

    def test_preview_has_no_filesystem_side_effect(self):
        self.target.write_bytes(b"# Existing\r\nKeep this.\r\n")
        before = self.target.read_bytes()
        result = anchor.configure(self.home)
        self.assertEqual(result["status"], "preview")
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(len(list(self.home.iterdir())), 1)

    def test_apply_preserves_original_bytes_and_backup(self):
        original = b"\xef\xbb\xbf# Existing\r\nPrivate setting stays.\r\n"
        self.target.write_bytes(original)
        result = anchor.configure(self.home, apply=True)
        self.assertEqual(result["status"], "applied")
        self.assertTrue(self.target.read_bytes().startswith(original))
        self.assertEqual(Path(result["backup"]).read_bytes(), original)
        self.assertNotIn(b"\n", self.target.read_bytes().replace(b"\r\n", b""))

    def test_second_apply_is_idempotent(self):
        anchor.configure(self.home, apply=True)
        first = self.target.read_bytes()
        result = anchor.configure(self.home, apply=True)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(self.target.read_bytes(), first)
        self.assertEqual(len(list(self.home.iterdir())), 1)

    def test_remove_preserves_unrelated_content(self):
        self.target.write_bytes(b"# Before\n")
        anchor.configure(self.home, apply=True)
        with self.target.open("ab") as handle:
            handle.write(b"\n# Added later\nKeep later work.\n")
        result = anchor.configure(self.home, apply=True, remove=True)
        content = self.target.read_bytes()
        self.assertEqual(result["status"], "applied")
        self.assertNotIn(anchor.START.encode(), content)
        self.assertTrue(content.startswith(b"# Before\n"))
        self.assertTrue(content.endswith(b"# Added later\nKeep later work.\n"))

    def test_remove_preview_does_not_write(self):
        anchor.configure(self.home, apply=True)
        original = self.target.read_bytes()
        self.assertEqual(anchor.configure(self.home, remove=True)["status"], "preview")
        self.assertEqual(self.target.read_bytes(), original)

    def test_absent_removal_creates_nothing(self):
        self.assertEqual(anchor.configure(self.home, apply=True, remove=True)["status"], "unchanged")
        self.assertFalse(self.target.exists())

    def test_nonempty_override_blocks(self):
        (self.home / "AGENTS.override.md").write_text("# Overrides", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "override"):
            anchor.configure(self.home, apply=True)
        self.assertFalse(self.target.exists())

    def test_empty_override_allowed(self):
        (self.home / "AGENTS.override.md").write_text(" \n", encoding="utf-8")
        self.assertEqual(anchor.configure(self.home, apply=True)["status"], "applied")

    def test_missing_directory_not_created(self):
        path = self.home / "missing"
        with self.assertRaises(ValueError):
            anchor.configure(path, apply=True)
        self.assertFalse(path.exists())

    def test_invalid_markers_block_without_write(self):
        for value in (anchor.START, anchor.END, anchor.END + anchor.START,
                      anchor.START + anchor.END + anchor.START + anchor.END):
            self.target.write_text(value, encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                anchor.configure(self.home, apply=True)
            self.assertEqual(self.target.read_text(encoding="utf-8"), value)

    def test_directory_target_blocks(self):
        self.target.mkdir()
        with self.assertRaises(ValueError):
            anchor.configure(self.home, apply=True)

    def test_invalid_utf8_blocks_without_write(self):
        self.target.write_bytes(b"\xff\xfeinvalid")
        with self.assertRaises(UnicodeError):
            anchor.configure(self.home, apply=True)
        self.assertEqual(self.target.read_bytes(), b"\xff\xfeinvalid")

    def test_update_only_replaces_managed_block(self):
        old = b"prefix\n" + anchor.START.encode() + b"\nstale\n" + anchor.END.encode() + b"\nsuffix"
        result = anchor.proposed_bytes(old, "fresh")
        self.assertTrue(result.startswith(b"prefix\n"))
        self.assertTrue(result.endswith(b"\nsuffix"))
        self.assertIn(b"fresh", result)
        self.assertNotIn(b"stale", result)

    def test_drive_root_and_user_home_rejected(self):
        for path in (Path(self.home.anchor), Path.home()):
            with self.subTest(path=path), self.assertRaises(ValueError):
                anchor.safe_target(path)

    def test_empty_or_whitespace_home_rejected(self):
        for value in ("", " ", "\t"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                anchor.resolve_home(value)
        self.assertEqual(anchor.resolve_home(None), Path.home() / ".codex")

    def test_dotdot_cannot_bypass_root_checks(self):
        for path in (Path.home() / "unused" / "..", Path(self.home.anchor) / "unused" / ".."):
            with self.subTest(path=path), self.assertRaises(ValueError):
                anchor.safe_target(path)

    def test_reparse_attribute_blocks_without_new_path_api(self):
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_file_attributes=0x400)):
            self.assertTrue(anchor.is_link(self.home))
            with self.assertRaisesRegex(ValueError, "Linked"):
                anchor.configure(self.home, apply=True)

    def test_backup_requests_private_posix_mode(self):
        self.target.write_text("existing", encoding="utf-8")
        original_open = os.open
        with patch.object(anchor.os, "open", wraps=original_open) as calls:
            result = anchor.configure(self.home, apply=True)
        backup_calls = [c for c in calls.call_args_list if str(c.args[0]).endswith(".bak")]
        self.assertEqual(len(backup_calls), 1)
        self.assertEqual(backup_calls[0].args[2], 0o600)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(Path(result["backup"]).stat().st_mode), 0o600)

    def test_symlink_target_rejected(self):
        external = self.home / "original.md"
        external.write_text("original", encoding="utf-8")
        try:
            self.target.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not available on this host")
        with self.assertRaises(ValueError):
            anchor.configure(self.home, apply=True)
        self.assertEqual(external.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
