"""Check, install, and automatically apply integrity-checked Porthex releases.

The transport trust boundary is the public GitHub release. Each release must contain
WindowsPorthexTheme.zip and WindowsPorthexTheme.zip.sha256. Updates are staged,
SHA-256 checked, validated, backed up, installed, and rolled back on failure.
The checksum detects corruption; GitHub account/release security is the trust root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "@Resources"
USER_SETTINGS = RESOURCES / "UserSettings.inc"
STATE_INC = RESOURCES / "UpdateState.inc"
SETTINGS_INI = ROOT / "Settings" / "Settings.ini"
PROFILE_INC = RESOURCES / "Profile.inc"
INSTALLED_MANIFEST = ROOT / "package-manifest.json"
RAINMETER = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Rainmeter" / "Rainmeter.exe"
ASSET_NAME = "WindowsPorthexTheme.zip"
CHECKSUM_NAME = ASSET_NAME + ".sha256"
PRESERVE = {
    "@Resources/UserSettings.inc",
    "@Resources/Profile.inc",
    "@Resources/GoogleData.inc",
    "@Resources/ServerData.inc",
    "@Resources/TaskbarStatusHost.state.json",
}
MUTEX_NAME = "Local\\WindowsPorthexThemeUpdater"


def parse_inc(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.is_file():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in raw and not raw.lstrip().startswith(";"):
                key, value = raw.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def safe(value: object, limit: int = 90) -> str:
    return " ".join(str(value).replace("#", " ").replace("=", " ").split())[:limit]


def write_state(**updates: str) -> None:
    current = parse_inc(STATE_INC)
    current.update({key: safe(value) for key, value in updates.items()})
    order = [
        "AutoUpdate", "AutoUpdateLabel", "InstalledVersion", "LatestVersion", "UpdateState",
        "UpdateDetail", "UpdateColor", "LastChecked", "ProfileState",
        "ProfileDetail", "ProfileColor",
    ]
    text = "".join(f"{key}={current.get(key, '')}\n" for key in order)
    temp = STATE_INC.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, STATE_INC)
    if SETTINGS_INI.is_file():
        source = SETTINGS_INI.read_text(encoding="utf-8-sig")
        for key in order:
            if re.search(rf"(?m)^{re.escape(key)}=", source):
                source = re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={current.get(key, '')}", source, count=1)
        settings_temp = SETTINGS_INI.with_suffix(".tmp")
        settings_temp.write_text(source, encoding="utf-8")
        os.replace(settings_temp, SETTINGS_INI)


def refresh_settings() -> None:
    if RAINMETER.is_file():
        subprocess.run(
            [str(RAINMETER), "!Refresh", r"WindowsPorthexTheme\Settings"],
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "WindowsPorthexTheme-Updater"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "WindowsPorthexTheme-Updater"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+){1,3})", value)
    return tuple(int(part) for part in match.group(1).split(".")) if match else (0,)


def latest_release() -> tuple[dict, dict[str, dict]]:
    repo = parse_inc(USER_SETTINGS).get("ReleaseRepo", "porthex/windows-porthex-theme")
    release = request_json(f"https://api.github.com/repos/{repo}/releases/latest")
    assets = {asset["name"]: asset for asset in release.get("assets", [])}
    if ASSET_NAME not in assets or CHECKSUM_NAME not in assets:
        raise RuntimeError("Latest release is missing its package or checksum")
    return release, assets


def installed_version() -> str:
    try:
        return str(json.loads(INSTALLED_MANIFEST.read_text(encoding="utf-8-sig"))["version"])
    except Exception:
        return parse_inc(STATE_INC).get("InstalledVersion", "0.0.0")


def check() -> tuple[bool, str, dict, dict[str, dict]]:
    write_state(UpdateState="CHECKING", UpdateDetail="Contacting GitHub...", UpdateColor="216,210,197,255")
    refresh_settings()
    release, assets = latest_release()
    latest = str(release.get("tag_name", "")).lstrip("v")
    installed = installed_version()
    available = version_tuple(latest) > version_tuple(installed)
    write_state(
        AutoUpdate=parse_inc(USER_SETTINGS).get("AutoUpdate", "0"),
        AutoUpdateLabel="ON" if parse_inc(USER_SETTINGS).get("AutoUpdate", "0") == "1" else "OFF",
        InstalledVersion=installed,
        LatestVersion=latest,
        UpdateState="UPDATE AVAILABLE" if available else "UP TO DATE",
        UpdateDetail="Select INSTALL UPDATE to apply it." if available else "This installation matches the latest release.",
        UpdateColor="218,168,92,255" if available else "95,210,140,255",
        LastChecked=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    refresh_settings()
    return available, latest, release, assets


def read_checksum(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise RuntimeError("Release checksum file is invalid")
    return token


def validate_zip_member(name: str) -> None:
    normalized = name.replace("\\", "/")
    candidate = normalized.rstrip("/")
    parts = candidate.split("/")
    if (
        not candidate
        or "\x00" in candidate
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", candidate)
        or any(part in ("", ".", "..") or ":" in part for part in parts)
    ):
        raise RuntimeError(f"Unsafe path in release: {name}")


def normalize_manifest_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("Package manifest contains an invalid path")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if Path(normalized).is_absolute() or normalized.startswith("/") or any(part in ("", ".", "..") or ":" in part for part in parts):
        raise RuntimeError(f"Unsafe path in package manifest: {value}")
    return "/".join(parts)


def validate_manifest(manifest: object, source: Path, expected_version: str) -> set[str]:
    if not isinstance(manifest, dict) or manifest.get("package") != "WindowsPorthexTheme":
        raise RuntimeError("Package manifest identity is invalid")
    if str(manifest.get("version")) != expected_version:
        raise RuntimeError("Release tag and package version do not match")
    values = manifest.get("files")
    if not isinstance(values, list):
        raise RuntimeError("Package manifest file list is invalid")
    files = [normalize_manifest_path(value) for value in values]
    if len(files) != len(set(files)):
        raise RuntimeError("Package manifest contains duplicate paths")
    actual = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file() and path.name != "package-manifest.json"}
    if set(files) != actual:
        raise RuntimeError("Package manifest does not exactly match staged files")
    return set(files)


def confined_target(relative: str) -> Path:
    normalized = normalize_manifest_path(relative)
    target = (ROOT / Path(*normalized.split("/"))).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError as error:
        raise RuntimeError(f"Manifest path escapes installation: {relative}") from error
    return target


@contextmanager
def updater_lock():
    if os.name != "nt":
        yield
        return
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        raise OSError("Could not create updater mutex")
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        raise RuntimeError("Another Porthex update is already running")
    try:
        yield
    finally:
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


def install() -> str:
    available, latest, _release, assets = check()
    if not available:
        return "up-to-date"
    write_state(UpdateState="INSTALLING", UpdateDetail="Verifying and staging the release...", UpdateColor="216,210,197,255")
    refresh_settings()
    with tempfile.TemporaryDirectory(prefix="porthex-theme-update-") as temp_value:
        temp = Path(temp_value)
        archive = temp / ASSET_NAME
        checksum = temp / CHECKSUM_NAME
        download(assets[ASSET_NAME]["browser_download_url"], archive)
        download(assets[CHECKSUM_NAME]["browser_download_url"], checksum)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        expected = read_checksum(checksum)
        if actual != expected:
            raise RuntimeError("Release SHA-256 verification failed")
        staging = temp / "staging"
        with zipfile.ZipFile(archive) as package:
            for member in package.namelist():
                validate_zip_member(member)
            package.extractall(staging)
        source = staging / "WindowsPorthexTheme"
        manifest_path = source / "package-manifest.json"
        if not manifest_path.is_file() or not (source / "Settings" / "Settings.ini").is_file() or not (source / "TopBar" / "TopBar.ini").is_file():
            raise RuntimeError("Release package structure is invalid")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        new_files = validate_manifest(manifest, source, latest)
        backup_root = ROOT.parent.parent / "Backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"WindowsPorthexTheme-before-{latest}-{datetime.now():%Y%m%d-%H%M%S}"
        replacement = ROOT.parent / f".{ROOT.name}-replacement-{os.getpid()}"
        displaced = ROOT.parent / f".{ROOT.name}-previous-{os.getpid()}"
        shutil.copytree(ROOT, backup)
        preserved = {name: confined_target(name).read_bytes() for name in PRESERVE if confined_target(name).is_file()}
        shutil.copytree(source, replacement)
        for name, content in preserved.items():
            target = replacement / Path(*normalize_manifest_path(name).split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        swapped = False
        try:
            ROOT.rename(displaced)
            try:
                replacement.rename(ROOT)
                swapped = True
            except Exception:
                displaced.rename(ROOT)
                raise
            write_state(
                AutoUpdate=parse_inc(USER_SETTINGS).get("AutoUpdate", "0"),
                AutoUpdateLabel="ON" if parse_inc(USER_SETTINGS).get("AutoUpdate", "0") == "1" else "OFF",
                InstalledVersion=latest,
                LatestVersion=latest,
                UpdateState="UPDATED",
                UpdateDetail=f"Version {latest} installed. Backup created.",
                UpdateColor="95,210,140,255",
                LastChecked=datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
            if installed_version() != latest:
                raise RuntimeError("Post-install version verification failed")
        except Exception:
            if swapped:
                failed = ROOT.parent / f".{ROOT.name}-failed-{os.getpid()}"
                ROOT.rename(failed)
                try:
                    displaced.rename(ROOT)
                except Exception as rollback_error:
                    failed.rename(ROOT)
                    raise RuntimeError(f"Update failed and rollback could not restore the previous tree: {rollback_error}") from rollback_error
                shutil.rmtree(failed, ignore_errors=True)
            raise
        else:
            shutil.rmtree(displaced, ignore_errors=True)
        finally:
            shutil.rmtree(replacement, ignore_errors=True)
    if RAINMETER.is_file():
        subprocess.Popen([str(RAINMETER), "!RefreshApp"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return latest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "install", "auto"))
    args = parser.parse_args()
    try:
        with updater_lock():
            if args.action == "check":
                available, latest, *_ = check()
                print(json.dumps({"available": available, "latest": latest, "installed": installed_version()}))
            elif args.action == "install":
                print(json.dumps({"installed": install()}))
            else:
                if parse_inc(USER_SETTINGS).get("AutoUpdate", "0") == "1":
                    print(json.dumps({"auto": True, "result": install()}))
                else:
                    print(json.dumps({"auto": False, "result": "disabled"}))
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
        write_state(
            UpdateState="UPDATE ERROR",
            UpdateDetail=safe(f"{type(error).__name__}: {error}"),
            UpdateColor="184,104,88,255",
            LastChecked=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        refresh_settings()
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
