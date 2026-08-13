# AI setup contract

Use this document when an automated agent installs, repairs, or updates Windows Porthex Theme.

## Non-negotiable rules

1. Inspect the real destination before writing. Resolve Documents through Windows APIs; do not assume `C:\Users\<name>\Documents` or OneDrive.
2. Back up the existing theme and Rainmeter configuration before replacement.
3. Never package or transfer:
   - OAuth tokens;
   - SSH private keys;
   - Git credentials;
   - `GoogleData.inc` or `ServerData.inc` runtime payloads;
   - `TaskbarStatusHost.state.json`;
   - machine-specific absolute paths.
4. Use the GitHub Release archive, not `git clone` into Rainmeter's live `Skins` directory.
5. Verify `WindowsPorthexTheme.zip.sha256` before extracting.
6. Reject archive members containing absolute paths or `..` traversal.
7. Preserve `@Resources/UserSettings.inc` and `@Resources/Profile.inc` during updates.
8. Run GUI-facing actions as the interactive Windows user. A Rainmeter process in Session 0 is not a valid deployment.
9. Do not report profiles fixed until all three real desktop indices are exercised.
10. Do not report visual success from files, Rainmeter.ini, or window existence alone. Capture the actual desktop.

## Installation sequence

1. Record:
   - Windows version and display geometry;
   - interactive user/session;
   - Rainmeter executable/version;
   - actual skin path and `Rainmeter.ini` path;
   - loaded skin windows and active layouts;
   - scheduled tasks beginning with `Porthex` or `WindowsPorthex`.
2. Verify the release checksum.
3. Execute `Install.ps1` in the interactive user's context.
4. Open Settings and run profile setup/repair.
5. Verify desktop switches:
   ```powershell
   $controller = "$env:USERPROFILE\Documents\Rainmeter\Skins\WindowsPorthexTheme\@Resources\WorkspaceController.py"
   python $controller setup
   python $controller switch 1
   python $controller status
   python $controller switch 2
   python $controller status
   python $controller switch 3
   python $controller status
   ```
   Expected current indices: 0, 1, 2.
6. Verify every active skin contains a right-click **Porthex settings** action and that the action opens the canonical Settings skin.
7. Run manual update check and compare its latest version with the current GitHub Releases API response.
8. Toggle auto-update on, restart Rainmeter, verify persistence, and return it to the user's prior preference.
9. Validate helper tasks and bounded resource use.
10. Capture the actual settled desktop and inspect for overlap, clipping, fallback surfaces, mojibake, and taskbar obstruction.

## Update/release sequence

1. Work in a clean repository checkout, never in the live Rainmeter skin folder.
2. Run tests and static scans.
3. Build with `Build-Release.ps1 -Version X.Y.Z`.
4. Inspect `package-manifest.json` inside the archive.
5. Confirm excluded secrets/runtime files are absent.
6. Test installing the archive into a temporary skin tree.
7. Publish the zip and `.sha256` together in one GitHub Release.
8. Test Settings against the published release.
9. Test one real upgrade from the immediately previous release, including backup creation and user-setting preservation.

## Failure behavior

Fail closed. Leave the existing theme running and show `UPDATE ERROR` when:

- GitHub is unavailable;
- release assets are incomplete;
- checksum verification fails;
- package structure/version is wrong;
- extraction contains unsafe paths;
- backup or replacement fails.

Do not silently switch to the repository source archive: it has no release checksum contract and may contain developer-only files.
