import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("updater", ROOT / "@Resources" / "UpdateManager.py")
updater = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(updater)


class PackageTests(unittest.TestCase):
    def test_no_machine_specific_or_secret_material(self):
        forbidden = ("C:\\Users\\Memphis", "C:\\Users\\Acer", "D:\\Hermes", "BEGIN OPENSSH PRIVATE KEY", "gho_")
        for path in ROOT.rglob("*"):
            if not path.is_file() or "tests" in path.parts or ".git" in path.parts or "__pycache__" in path.parts or path.suffix.lower() in {".dll", ".png", ".zip", ".pyc"}:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            for token in forbidden:
                self.assertNotIn(token, text, f"{token} in {path}")

    def test_every_skin_exposes_settings(self):
        skins = [path for path in ROOT.glob("*/*.ini") if path.parent.name != "Settings"]
        self.assertTrue(skins)
        for path in skins:
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("Porthex settings", text, str(path))
            self.assertIn(r'WindowsPorthexTheme\Settings', text, str(path))

    def test_profile_controller_has_no_third_party_python_dependency(self):
        text = (ROOT / "@Resources" / "WorkspaceController.py").read_text(encoding="utf-8")
        self.assertNotIn("import psutil", text)
        self.assertIn("RainmeterMeterWindow", text)

    def test_version_comparison(self):
        self.assertGreater(updater.version_tuple("v1.2.0"), updater.version_tuple("1.1.9"))
        self.assertEqual(updater.version_tuple("1.0.0"), (1, 0, 0))

    def test_zip_traversal_rejected(self):
        with self.assertRaises(RuntimeError):
            updater.validate_zip_member("../escape.txt")
        updater.validate_zip_member("WindowsPorthexTheme/TopBar/TopBar.ini")

    def test_checksum_parser(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "x.sha256"
            path.write_text("a" * 64 + "  WindowsPorthexTheme.zip\n", encoding="utf-8")
            self.assertEqual(updater.read_checksum(path), "a" * 64)
            path.write_text("not-a-hash", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                updater.read_checksum(path)

    def test_check_reports_real_release_state_from_mocked_metadata(self):
        state = {}
        release = {"tag_name": "v1.1.0"}
        assets = {
            updater.ASSET_NAME: {"browser_download_url": "https://example/package"},
            updater.CHECKSUM_NAME: {"browser_download_url": "https://example/hash"},
        }
        with mock.patch.object(updater, "latest_release", return_value=(release, assets)), \
             mock.patch.object(updater, "installed_version", return_value="1.0.0"), \
             mock.patch.object(updater, "write_state", side_effect=lambda **kw: state.update(kw)), \
             mock.patch.object(updater, "refresh_settings"):
            available, latest, *_ = updater.check()
        self.assertTrue(available)
        self.assertEqual(latest, "1.1.0")
        self.assertEqual(state["UpdateState"], "UPDATE AVAILABLE")

    def test_installed_manifest_accepts_windows_utf8_bom(self):
        original = updater.INSTALLED_MANIFEST
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "package-manifest.json"
                manifest.write_text('{"version":"1.2.3"}', encoding="utf-8-sig")
                updater.INSTALLED_MANIFEST = manifest
                self.assertEqual(updater.installed_version(), "1.2.3")
        finally:
            updater.INSTALLED_MANIFEST = original

    def test_vbs_option_explicit_declarations_cover_runtime_paths(self):
        profile = (ROOT / "@Resources" / "SetProfile.vbs").read_text(encoding="utf-8-sig")
        settings = (ROOT / "@Resources" / "SettingsAction.vbs").read_text(encoding="utf-8-sig")
        self.assertRegex(profile, r"(?mi)^Dim .*\btopbar\b.*\bfield\b")
        self.assertRegex(settings, r"(?mi)^Dim .*\bsettingsIni\b")

    def test_runtime_variables_are_directly_declared(self):
        settings = (ROOT / "Settings" / "Settings.ini").read_text(encoding="utf-8-sig")
        topbar = (ROOT / "TopBar" / "TopBar.ini").read_text(encoding="utf-8-sig")
        field = (ROOT / "Field" / "Field.ini").read_text(encoding="utf-8-sig")
        for key in ("InstalledVersion", "LatestVersion", "UpdateState", "AutoUpdateLabel", "ProfileState"):
            self.assertRegex(settings, rf"(?m)^{key}=")
        for key in ("ProfileIndex", "ProfileName", "ProfileIndicatorX"):
            self.assertRegex(topbar, rf"(?m)^{key}=")
        self.assertRegex(field, r"(?m)^ProfileFieldBase=")

    def test_runtime_files_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for name in ("GoogleData.inc", "ServerData.inc", "*.state.json", "*.key", "*.pem"):
            self.assertIn(name, ignored)


if __name__ == "__main__":
    unittest.main()
