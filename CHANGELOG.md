# Changelog

Notable changes to 4u4free are recorded here.

## 0.5.4

- Changed DLC completion reporting to distinguish verified local files from
  runtime entitlement, which must be checked inside each game.

## 0.5.3

- Simplified DLC setup to an installed-game dropdown with automatic App ID and
  install-folder discovery.
- Made DLC catalogs load automatically when the selected game changes.
- Excluded soundtracks and other non-DLC app types from game DLC setup.
- Corrected nested Steam API inspection and CreamAPI/SmokeAPI status detection.
- Clarified when a local DLC setup requires a game restart rather than a Steam
  download, and replaced the misleading download-row action with Open folder.

## 0.5.2

- Updated the primary Store action label.
- Prepared the project for its public open-source release.
- Removed obsolete applications, build systems, assets, documentation, and
  third-party bundles that are not used by 4u4free.
- Consolidated required compatibility support under the main package.
- Changed tagged releases to publish the Windows installer and checksum only.
- Added continuous integration, tagged release builds, contribution guidance,
  issue templates, and security reporting instructions.

## 0.5.1

- Reworked the Tools page into a stable left-side navigator.
- Made Settings responsive at the minimum window size and added clear saved and
  unsaved state feedback.
- Standardized table sizing, empty states, spacing, typography, control styles,
  and navigation states throughout the desktop interface.
- Improved Store card alignment, pagination states, search feedback, and grid
  rendering.
- Added a visible active-task count without blocking unrelated navigation.

## 0.5.0

- Added Save Vault with per-game locations, versioned ZIP snapshots, SHA-256
  verification, and safety snapshots before restore.
- Added an opt-in local plugin framework with manifests, declared permissions,
  and per-plugin enablement. Plugins remain disabled by default and run with
  the user's full permissions when enabled.
- Added Steam statistics review through the bundled Steam Achievement Manager.
- Added read-only achievement showcase recommendations based on public global
  completion data.
- Improved Downloads with actionable provider errors and official Steam install
  actions for titles owned by the signed-in account.
- Extended configuration export and import for Save Vault and plugin settings.

## 0.4.2

- Added a credential-free headless playtime mode tied to the 4u4free process.
- Added library-wide achievement review while preserving explicit per-game
  confirmation and commit steps.
- Added lifecycle safeguards for helper startup, manual stop, goal completion,
  early Steam-side exits, and application shutdown.

## 0.4.1

- Added real-time playtime goals for installed games.
- Added Steam-running validation, elapsed and remaining progress, completion
  notifications, and manual tracking controls.
- Documented that playtime is never backdated or accelerated and that stopping
  the local timer does not force-close a running game.

## 0.4.0

- Added achievement management for installed games using Steam Achievement
  Manager 7.0.41.
- Added LC Online Fix controls with launch-option preservation, atomic writes,
  automatic backup, result verification, and conditional Steam restart.
- Added curated compatibility profiles for games requiring dedicated service
  replacements.
- Added an offline local compatibility probe for Steam API libraries,
  anti-cheat components, and common external backend SDKs.
- Added a pinned snapshot of SteamDB's MIT-licensed file-detection rules.

Upstream history for adapted compatibility code is recorded in
[ATTRIBUTION.md](ATTRIBUTION.md).
