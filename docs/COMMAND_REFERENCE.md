# 4u4free command reference

## Global behavior

`4u4free` requires Python 3.10 or newer and has no third-party runtime dependencies. Steam discovery uses this precedence:

1. `--steam-root`
2. Saved `steam_root` in `config.json`
3. `STEAM_ROOT` or `STEAM_PATH`
4. Valve registry keys on Windows
5. Standard platform install locations

An explicitly supplied invalid path fails; it never silently falls through to a different Steam installation. Expected user errors return exit code 2, an unsuccessful diagnostic or failed verification returns 1, Ctrl+C returns 130, and success returns 0.

## `doctor`

Checks Python/platform details, discovers Steam, and counts visible libraries and ACF manifests.

```text
4u4free doctor [--steam-root PATH] [--json]
```

This is read-only and is the recommended first command.

## `libraries`

Parses `Steam/steamapps/libraryfolders.vdf` and lists existing library roots. Duplicate paths are removed case-insensitively on Windows.

```text
4u4free libraries [--steam-root PATH] [--json]
```

## `games`

Reads `appmanifest_*.acf` in every discovered library. It emits App ID, display name, build ID, install directory, library, and manifest path. A malformed individual ACF is skipped rather than aborting the entire scan.

```text
4u4free games [--steam-root PATH] [--json]
```

## `profiles`

Reads `config/loginusers.vdf` and numeric directories under `userdata`. It reports local Steam/account IDs, account and persona names, recent-login state, and userdata roots. It does not read credentials or save contents.

```text
4u4free profiles [--steam-root PATH] [--json]
```

## `inspect-lua`

Reads, but never executes, a Lua metadata file. Supported directives are compatible with the subset analyzed in SteaMidra:

```lua
addappid(DEPOT_OR_APP_ID)
addappid(DEPOT_OR_APP_ID, FLAG, "64_HEX_CHARACTER_KEY")
setManifestid(DEPOT_ID, "MANIFEST_GID")
addtoken(APP_ID, "TOKEN")
```

Lua `--` line comments and `--[[ ... ]]` long comments are removed before parsing. The input limit is 8 MiB. Keys and tokens are redacted unless the user explicitly supplies `--show-secrets`.

```text
4u4free inspect-lua PATH [--show-secrets] [--json]
```

## `import-lua`

Parses the Lua, computes SHA-256, and stores an immutable content-addressed copy under 4u4free's own `imports` directory. Metadata written to SQLite is redacted. The raw archived source can still contain its original keys/tokens, so the data directory should remain private.

```text
4u4free import-lua PATH [--archive DIR] [--catalog FILE] [--json]
```

It does not install the Lua into Steam.

## `plan-import`

Prints the ordered actions needed by the analyzed SteaMidra-style flow and labels each action `ready` or `future`. It does not create files or alter Steam.

```text
4u4free plan-import PATH [--steam-root PATH] [--json]
```

## `scan`

Upserts current local ACF metadata into SQLite. The scan does not delete older catalog rows, so temporarily disconnected libraries remain queryable.

```text
4u4free scan [--catalog FILE] [--steam-root PATH] [--json]
```

## `catalog`

```text
4u4free catalog [--catalog FILE] games [--query TEXT] [--json]
4u4free catalog [--catalog FILE] lua [--app-id ID] [--json]
4u4free catalog [--catalog FILE] stats [--json]
```

The catalog schema is initialized on first access. Game searches match name or App ID.

## `backup`

Creates a new destination and copies only:

- `config/config.vdf`
- `steamapps/libraryfolders.vdf`
- `config/stplug-in/*.lua`
- `steamapps/appmanifest_*.acf` from every currently registered library

Symlinks are skipped. `backup-manifest.json` records the source, registered target root, allowlisted target path, relative archive path, byte size, and SHA-256 of every copied file. The destination must not already exist.

```text
4u4free backup [--output NEW_DIR] [--steam-root PATH] [--json]
```

## `verify-backup`

Rejects absolute paths, `..` traversal, paths outside the restore allowlist/archive layout, symlinks, missing files, and SHA-256 mismatches.

```text
4u4free verify-backup BACKUP_DIR [--json]
```

## `restore`

The default is a verified dry run. `--apply` first snapshots the current allowlisted Steam state to 4u4free's backup directory, then restores the requested files. Existing symlink path components cause a refusal.

```text
4u4free restore BACKUP_DIR [--steam-root PATH] [--apply] [--json]
```

Steam should be closed before a real restore to avoid competing writes. The program intentionally does not close Steam itself.

## `snapshot`

Creates a versioned JSON inventory containing discovered libraries, installed ACF metadata, and each manifest's SHA-256. Snapshot loading validates every record, rejects duplicate or malformed App IDs, and requires valid manifest hashes. Diffing reports added, removed, and field-level changed games without touching Steam.

```text
4u4free snapshot create OUTPUT [--steam-root PATH] [--force] [--json]
4u4free snapshot diff BEFORE AFTER [--json]
```

## `managed-lua`

Lists parseable `config/stplug-in/*.lua` files with keys and tokens redacted. Quarantine matches an App ID by filename, inferred App ID, parsed directive, or token owner. It previews by default. `--apply` creates a checksummed Steam-state backup first, then moves matching files to a timestamped quarantine directory. A failed multi-file move attempts to roll back already moved files and reports the snapshot path.

```text
4u4free managed-lua list [--steam-root PATH] [--json]
4u4free managed-lua quarantine APP_ID [--steam-root PATH] [--quarantine DIR]
    [--backup-output NEW_DIR] [--apply] [--json]
```

## `report`

Generates Markdown from the local Steam root, libraries, and installed manifests. Existing output files are preserved unless `--force` is supplied.

```text
4u4free report [--steam-root PATH] [--output FILE] [--force]
```

## `audit`

Reads recent JSONL events for backups, restores, catalog scans, Lua archival, and report creation. Event details exclude Lua keys/tokens.

```text
4u4free audit [--audit-file FILE] [--limit N] [--json]
```

## `config`

```text
4u4free config show
4u4free config set --steam-root PATH
4u4free config set --preferred-library PATH
4u4free config export OUTPUT [--force] [--json]
4u4free config import SOURCE [--apply] [--json]
```

Writes are atomic through a sibling temporary file and replacement. Exports contain only the versioned path configuration. Imports reject unknown fields and unsupported schema versions, preview by default, and back up an existing configuration before `--apply`. `preferred_library` is retained for a later feature phase but does not currently change discovery order.
