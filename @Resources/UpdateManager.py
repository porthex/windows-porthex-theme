"""Check, install, and automatically apply signed-by-hash Porthex theme releases.

The transport trust boundary is the public GitHub release. Each release must contain
WindowsPorthexTheme.zip and WindowsPorthexTheme.zip.sha256. Updates are staged,
SHA-256 verified, validated, backed up, installed, and rolled back on failure.
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
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "@Resources"
USER_SETTINGS = RESOURCES / "UserSettings.inc"
STATE_INC = RESOURCES / "UpdateState.inc"
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
        return str(json.loads(INSTALLED_MANIFEST.read_text(encoding="utf-8"))["version"])
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
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise RuntimeError(f"Unsafe path in release: {name}")


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
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(manifest.get("version")) != latest:
            raise RuntimeError("Release tag and package version do not match")
        backup_root = ROOT.parent.parent / "Backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"WindowsPorthexTheme-before-{latest}-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copytree(ROOT, backup)
        preserved = {name: (ROOT / name).read_bytes() for name in PRESERVE if (ROOT / name).is_file()}
        old_files = set()
        try:
            if INSTALLED_MANIFEST.is_file():
                old_files = set(json.loads(INSTALLED_MANIFEST.read_text(encoding="utf-8")).get("files", []))
            new_files = set(manifest.get("files", []))
            for relative in sorted(old_files - new_files - PRESERVE):
                target = ROOT / relative
                if target.is_file():
                    target.unlink()
            shutil.copytree(source, ROOT, dirs_exist_ok=True)
            for name, content in preserved.items():
                target = ROOT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        except Exception:
            shutil.rmtree(ROOT)
            shutil.copytree(backup, ROOT)
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
    if RAINMETER.is_file():
        subprocess.Popen([str(RAINMETER), "!RefreshApp"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return latest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "install", "auto"))
    args = parser.parse_args()
    try:
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
