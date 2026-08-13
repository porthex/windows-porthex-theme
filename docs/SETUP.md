# Setup and recovery

## 1. Prerequisites

1. Install current Rainmeter to `C:\Program Files\Rainmeter`.
2. Install Python 3.11, 3.12, or 3.13 for the current Windows user.
3. Confirm the Windows user has an interactive desktop session.
4. Download the latest `WindowsPorthexTheme.zip` and `.sha256` from GitHub Releases.

Verify the release before extraction:

```powershell
$expected = (Get-Content .\WindowsPorthexTheme.zip.sha256).Split()[0]
$actual = (Get-FileHash .\WindowsPorthexTheme.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw 'Checksum mismatch' }
```

## 2. Install

```powershell
Expand-Archive .\WindowsPorthexTheme.zip -DestinationPath .\PorthexRelease
powershell -ExecutionPolicy Bypass -File .\PorthexRelease\WindowsPorthexTheme\Install.ps1
```

The installer:

- backs up an existing installation;
- installs to the actual Windows Documents/Rainmeter path;
- registers user-level logon tasks for the taskbar helper and server monitor when Python exists;
- registers a logon/daily auto-update check (it stays inert while auto-update is off);
- creates and names three native Windows desktops;
- opens the Settings skin.

## 3. Profiles

Open Settings and select **SETUP / REPAIR**. The top bar buttons map as follows:

- `01` → Quiet
- `02` → Work
- `03` → Deep Focus

The profiles are real Windows virtual desktops. The theme updates the active profile label and field opacity only after the Windows desktop API reports a successful switch.

If profiles fail:

1. Confirm `python --version` works.
2. Confirm `@Resources\VirtualDesktopAccessor.dll` exists.
3. Run:
   ```powershell
   python "$env:USERPROFILE\Documents\Rainmeter\Skins\WindowsPorthexTheme\@Resources\WorkspaceController.py" setup
   ```
4. The JSON result must report `count` of at least 3.
5. Run each switch and verify `current` becomes 0, 1, and 2.

## 4. Optional integrations

### Google Calendar and Gmail

Google data is disabled until the user completes OAuth separately. The token belongs at:

`%LOCALAPPDATA%\PorthexRainmeter\google_widget_token.json`

Do not copy or commit another computer's token. Required OAuth scopes are Calendar read-only and Gmail read-only.

### Private server panel

The default panel expects a key-only SSH host alias `hermes-cloud`. Configure `@Resources\UserSettings.inc` for another host. Never add private keys or passwords to the theme.

## 5. Settings and updates

Right-click any Porthex skin and select **Porthex settings**.

- **CHECK UPDATE** only reads release metadata.
- **INSTALL UPDATE** downloads and verifies the release, backs up the current installation, and refreshes Rainmeter.
- **AUTO UPDATE 0/1** toggles automatic install checks at logon and daily.

Backups are stored under the user's `Documents\Rainmeter\Backups` directory.

## 6. Acceptance checks

Do not call installation complete based only on copied files.

1. Rainmeter runs in the interactive user session.
2. TopBar and Field are live windows using canonical `.ini` paths.
3. Calendar, Email, Server, and Settings render without white fallback rectangles or clipping.
4. Each profile button changes the real Windows desktop index.
5. Right-click each visible skin and verify **Porthex settings** opens Settings.
6. Settings can toggle auto-update, and the value persists after Rainmeter restart.
7. Update check displays the actual GitHub release version.
8. Taskbar helper does not cover Start, pinned apps, tray, or clock.
9. No credential, OAuth token, private key, username-specific path, or runtime cache exists in the package.
10. Take an actual desktop screenshot after state settles.

## 7. Recovery

If an update fails, the updater restores its pre-update backup automatically for file-deployment failures. For manual recovery:

1. Exit Rainmeter.
2. Rename the current `WindowsPorthexTheme` folder.
3. Copy the newest matching backup from `Documents\Rainmeter\Backups` into `Documents\Rainmeter\Skins\WindowsPorthexTheme`.
4. Start Rainmeter and use **Refresh all**.

The installer and updater do not delete unrelated skins or Windows virtual desktops.
