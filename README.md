# Windows Porthex Theme

A near-black, graphite, and warm-silver Rainmeter desktop for Windows 11. It includes:

- a full-width status bar;
- Quiet, Work, and Deep Focus native Windows virtual-desktop profiles;
- a low-motion desktop field;
- optional Calendar, recent Gmail, and private-server panels;
- a compact settings panel;
- manual update checks, update-available status, and optional automatic updates from GitHub Releases.

## Install

Requirements:

- Windows 11
- [Rainmeter](https://www.rainmeter.net/)
- Python 3.11–3.13 for profiles and helper processes

Download `WindowsPorthexTheme.zip` and its `.sha256` file from the latest release. Verify the hash, extract it, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\WindowsPorthexTheme\Install.ps1
```

See [docs/SETUP.md](docs/SETUP.md) for the complete setup and verification procedure.

## Settings and updates

Right-click any Porthex widget and select **Porthex settings**.

The settings panel provides:

- installed and latest release versions;
- `UP TO DATE`, `UPDATE AVAILABLE`, or error state;
- **Check update** and **Install update** actions;
- an **Auto update** switch (`OFF` or `ON`);
- profile setup/repair;
- repository and setup-guide links.

Updates are downloaded from the public GitHub Releases API. The updater requires both `WindowsPorthexTheme.zip` and `WindowsPorthexTheme.zip.sha256`, verifies SHA-256 before extraction, rejects path traversal, backs up the active skin, preserves user/runtime settings, and rolls back a failed file deployment.

## Safe local configuration

Machine-specific values live in `@Resources/UserSettings.inc`. Runtime state and credentials are not committed or released. In particular, Google OAuth tokens remain under `%LOCALAPPDATA%\PorthexRainmeter` unless the user explicitly selects another path.

The Server panel is optional and assumes a key-only SSH alias. Edit these values if needed:

```ini
ServerHost=hermes-cloud
ServerAddress=hermes-cloud.tailaf56f1.ts.net
ServerPort=2222
```

## Repository layout

- `TopBar`, `Field`, `Calendar`, `Email`, `Server`, `TaskbarStatus`, `Settings`: Rainmeter skins
- `@Resources`: shared assets and helpers
- `Install.ps1`: reversible installer/task setup
- `Build-Release.ps1`: deterministic release-package builder
- `docs/SETUP.md`: human setup guide
- `docs/AI-SETUP-GUIDE.md`: fail-closed setup guide for automation agents
- `tests`: offline package and updater tests

## Release process

```powershell
powershell -File .\Build-Release.ps1 -Version 1.0.0

gh release create v1.0.0 `
  .\dist\WindowsPorthexTheme.zip `
  .\dist\WindowsPorthexTheme.zip.sha256 `
  --title "Windows Porthex Theme v1.0.0" `
  --generate-notes
```

Never publish directly from a live Rainmeter directory. Build from a clean repository checkout and inspect the generated manifest and archive first.

## Third-party component

`@Resources/VirtualDesktopAccessor.dll` is from [Ciantic/VirtualDesktopAccessor](https://github.com/Ciantic/VirtualDesktopAccessor), distributed under the MIT License. Its license is included at `THIRD_PARTY_NOTICES.md`.

## License

MIT. See [LICENSE](LICENSE).
