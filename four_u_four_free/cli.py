"""Command-line interface for 4u4free."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from . import __version__
from .audit import AuditLog
from .backup import create_backup
from .catalog import Catalog
from .config import ConfigStore
from .errors import FourUFourFreeError
from .integrity import restore_backup, verify_backup
from .lua import inspect_lua
from .managed import list_managed_lua, quarantine_managed_lua
from .planner import make_import_plan
from .profiles import list_profiles
from .report import environment_report
from .settings_io import export_config, import_config
from .snapshots import compare_snapshots, create_inventory_snapshot, load_snapshot, write_snapshot
from .steam import doctor, list_games, list_libraries, require_steam_root

try:
    from sff.dlc_unlockers.base import UnlockerType
    from sff.dlc_unlockers.creamapi import CreamAPIUnlocker
    from sff.dlc_unlockers.smokeapi import SmokeAPIUnlocker
    from sff.dlc_unlockers.uplay_r1 import UplayR1Unlocker
    from sff.dlc_unlockers.uplay_r2 import UplayR2Unlocker
    from sff.dlc_unlockers.downloader import GitHubReleaseDownloader
    from sff.dlc_unlockers.validation import (
        validate_game_directory,
        validate_app_id,
        validate_dlc_ids,
    )
    from sff.lumacore.lumacore_setup import (
        install_lumacore,
        deactivate_lumacore,
        get_installed_lumacore_version,
        check_for_lumacore_update,
    )
    from sff.game.fix_game.steamstub_unpacker import SteamStubUnpacker
    from sff.game.crack_fix import fetch_crack_games, search_crack_games, apply_crack_fix
    HAS_SFF = True
    SFF_IMPORT_ERROR = ""
except ImportError as _exc:
    HAS_SFF = False
    SFF_IMPORT_ERROR = str(_exc)


def _json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _root(args, store: ConfigStore):
    config = store.load()
    explicit = Path(args.steam_root) if getattr(args, "steam_root", None) else None
    return require_steam_root(explicit, config.steam_root)


def _print_rows(rows: Iterable[Iterable[object]]) -> None:
    materialized = [[str(cell) for cell in row] for row in rows]
    if not materialized:
        return
    widths = [max(len(row[column]) for row in materialized) for column in range(len(materialized[0]))]
    for row in materialized:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip())


def cmd_doctor(args, store: ConfigStore) -> int:
    config = store.load()
    report = doctor(Path(args.steam_root) if args.steam_root else None, config.steam_root)
    if args.json:
        _json(report)
    else:
        _print_rows((key.replace("_", " ").title(), value) for key, value in report.items())
    return 0 if report["steam_found"] else 1


def cmd_libraries(args, store: ConfigStore) -> int:
    location = _root(args, store)
    libraries = list_libraries(location.path)
    if args.json:
        _json({"steam_root": str(location.path), "source": location.source, "libraries": [str(path) for path in libraries]})
    else:
        for path in libraries:
            print(path)
    return 0


def cmd_games(args, store: ConfigStore) -> int:
    location = _root(args, store)
    games = list_games(list_libraries(location.path))
    if args.json:
        _json([game.to_dict() for game in games])
    else:
        rows = [("APP ID", "NAME", "BUILD", "LIBRARY")]
        rows.extend((game.app_id, game.name, game.build_id or "-", game.library) for game in games)
        _print_rows(rows)
    return 0


def cmd_profiles(args, store: ConfigStore) -> int:
    location = _root(args, store)
    profiles = list_profiles(location.path)
    if args.json:
        _json([profile.to_dict() for profile in profiles])
    else:
        rows = [("STEAM ID", "ACCOUNT", "PERSONA", "RECENT", "USERDATA")]
        rows.extend(
            (
                profile.steam_id64 or "-",
                profile.account_name or profile.account_id,
                profile.persona_name or "-",
                "yes" if profile.most_recent else "no",
                profile.userdata,
            )
            for profile in profiles
        )
        _print_rows(rows)
    return 0


def cmd_inspect_lua(args, _store: ConfigStore) -> int:
    info = inspect_lua(Path(args.path))
    payload = info.to_dict(show_secrets=args.show_secrets)
    if args.json:
        _json(payload)
    else:
        print(f"File: {payload['path']}")
        print(f"Inferred app ID: {payload['inferred_app_id'] or '-'}")
        for name, count in payload["counts"].items():
            print(f"{name.replace('_', ' ').title()}: {count}")
        if info.app_directives:
            print("\nApp/depot directives:")
            for directive in payload["app_directives"]:
                print(f"  {directive['app_or_depot_id']}  flag={directive['flag'] or '-'}  key={directive['key'] or '-'}")
        if info.manifests:
            print("\nManifest pins:")
            for depot, gid in info.manifests.items():
                print(f"  {depot} -> {gid}")
        if info.tokens:
            print("\nTokens:")
            for token in payload["tokens"]:
                print(f"  {token['app_id']} -> {token['token']}")
    return 0


def cmd_plan_import(args, store: ConfigStore) -> int:
    location = _root(args, store)
    plan = make_import_plan(inspect_lua(Path(args.path)), location.path)
    payload = plan.to_dict()
    if args.json:
        _json(payload)
    else:
        print(f"Dry-run import plan for {payload['source_lua']}")
        for action in plan.actions:
            status = "ready" if action.implemented else "future"
            print(f"  {action.order}. [{status}] {action.description}")
            print(f"     {action.target}")
        print("\nWarnings:")
        for warning in plan.warnings:
            print(f"  - {warning}")
    return 0


def cmd_backup(args, store: ConfigStore) -> int:
    location = _root(args, store)
    result = create_backup(
        location.path,
        Path(args.output) if args.output else None,
        list_libraries(location.path),
    )
    AuditLog().record("backup.created", result.to_dict())
    if args.json:
        _json(result.to_dict())
    else:
        print(f"Backup created: {result.destination}")
        print(f"Files copied: {len(result.files)}")
        print(f"Manifest: {result.manifest}")
    return 0


def cmd_verify_backup(args, _store: ConfigStore) -> int:
    result = verify_backup(Path(args.backup))
    if args.json:
        _json(result.to_dict())
    else:
        print(f"Backup: {result.backup}")
        print(f"Valid: {'yes' if result.valid else 'no'}")
        print(f"Files checked: {result.checked}")
        if result.missing:
            print("Missing: " + ", ".join(result.missing))
        if result.mismatched:
            print("Hash mismatches: " + ", ".join(result.mismatched))
    return 0 if result.valid else 1


def cmd_restore(args, store: ConfigStore) -> int:
    location = _root(args, store)
    result = restore_backup(Path(args.backup), location.path, apply=args.apply)
    if result["applied"]:
        AuditLog().record("backup.restored", result)
    if args.json:
        _json(result)
    elif not result["applied"]:
        print("Restore plan verified. No files were changed.")
        for target in result["targets"]:
            print(f"  {target}")
        print("Run again with --apply to restore these files after an automatic pre-restore backup.")
    else:
        print(f"Restored {len(result['restored'])} files.")
        print(f"Pre-restore backup: {result['pre_restore_backup']}")
    return 0


def cmd_snapshot_create(args, store: ConfigStore) -> int:
    location = _root(args, store)
    snapshot = create_inventory_snapshot(location.path)
    destination = write_snapshot(snapshot, Path(args.output), force=args.force)
    payload = {
        "snapshot": str(destination),
        "steam_root": snapshot["steam_root"],
        "libraries": len(snapshot["libraries"]),
        "games": len(snapshot["games"]),
    }
    AuditLog().record("snapshot.created", payload)
    if args.json:
        _json(payload)
    else:
        print(f"Snapshot written: {destination}")
        print(f"Libraries: {payload['libraries']}")
        print(f"Games: {payload['games']}")
    return 0


def cmd_snapshot_diff(args, _store: ConfigStore) -> int:
    result = compare_snapshots(load_snapshot(Path(args.before)), load_snapshot(Path(args.after)))
    if args.json:
        _json(result)
    else:
        counts = result["counts"]
        print(f"Added: {counts['added']}  Removed: {counts['removed']}  Changed: {counts['changed']}")
        for game in result["added"]:
            print(f"  + {game.get('app_id', '-')}  {game.get('name', 'Unknown')}")
        for game in result["removed"]:
            print(f"  - {game.get('app_id', '-')}  {game.get('name', 'Unknown')}")
        for game in result["changed"]:
            fields = ", ".join(game["changes"])
            print(f"  ~ {game['app_id']}  {fields}")
    return 0


def cmd_managed_list(args, store: ConfigStore) -> int:
    location = _root(args, store)
    files = list_managed_lua(location.path)
    if args.json:
        _json([info.to_dict(show_secrets=False) for info in files])
    else:
        rows = [("APP ID", "APPS/DEPOTS", "MANIFESTS", "TOKENS", "FILE")]
        rows.extend(
            (
                info.inferred_app_id or "-",
                len(info.app_directives),
                len(info.manifests),
                len(info.tokens),
                info.path,
            )
            for info in files
        )
        _print_rows(rows)
    return 0


def cmd_managed_quarantine(args, store: ConfigStore) -> int:
    location = _root(args, store)
    result = quarantine_managed_lua(
        location.path,
        args.app_id,
        apply=args.apply,
        quarantine_root=Path(args.quarantine) if args.quarantine else None,
        backup_output=Path(args.backup_output) if args.backup_output else None,
    )
    if result["applied"]:
        AuditLog().record("lua.quarantined", result)
    if args.json:
        _json(result)
    elif not result["files"]:
        print(f"No managed Lua files matched App ID {args.app_id}.")
    elif not result["applied"]:
        print(f"Quarantine preview for App ID {args.app_id}; no files were changed.")
        for path in result["files"]:
            print(f"  {path}")
        print("Run again with --apply to create a backup and quarantine these files.")
    else:
        print(f"Quarantined {len(result['moved'])} file(s) in {result['quarantine']}")
        print(f"Pre-change backup: {result['snapshot']}")
    return 0


def cmd_scan(args, store: ConfigStore) -> int:
    location = _root(args, store)
    games = list_games(list_libraries(location.path))
    catalog = Catalog(Path(args.catalog) if args.catalog else None)
    count = catalog.sync_games(games)
    AuditLog().record("catalog.scanned", {"catalog": str(catalog.path), "games": count, "steam_root": str(location.path)})
    payload = {"catalog": str(catalog.path), "games_indexed": count, "steam_root": str(location.path)}
    if args.json:
        _json(payload)
    else:
        print(f"Indexed {count} installed game manifests into {catalog.path}")
    return 0


def cmd_import_lua(args, _store: ConfigStore) -> int:
    catalog = Catalog(Path(args.catalog) if args.catalog else None)
    result = catalog.import_lua(Path(args.path), Path(args.archive) if args.archive else None)
    AuditLog().record(
        "lua.archived",
        {"sha256": result.sha256, "archived_path": str(result.archived_path), "already_present": result.already_present},
    )
    if args.json:
        _json(result.to_dict())
    else:
        status = "already archived" if result.already_present else "archived"
        print(f"Lua metadata {status}: {result.archived_path}")
        print(f"SHA-256: {result.sha256}")
        print("The file was parsed but not executed or installed into Steam.")
    return 0


def cmd_catalog_games(args, _store: ConfigStore) -> int:
    catalog = Catalog(Path(args.catalog) if args.catalog else None)
    rows = catalog.games(args.query)
    if args.json:
        _json(rows)
    else:
        table = [("APP ID", "NAME", "BUILD", "LIBRARY")]
        table.extend((row["app_id"], row["name"], row["build_id"] or "-", row["library"]) for row in rows)
        _print_rows(table)
    return 0


def cmd_catalog_lua(args, _store: ConfigStore) -> int:
    catalog = Catalog(Path(args.catalog) if args.catalog else None)
    rows = catalog.lua_files(args.app_id)
    if args.json:
        _json(rows)
    else:
        table = [("APP ID", "SHA-256", "ARCHIVED FILE")]
        table.extend((row["inferred_app_id"] or "-", row["sha256"], row["archived_path"]) for row in rows)
        _print_rows(table)
    return 0


def cmd_catalog_stats(args, _store: ConfigStore) -> int:
    catalog = Catalog(Path(args.catalog) if args.catalog else None)
    payload = catalog.stats()
    if args.json:
        _json(payload)
    else:
        _print_rows((key.replace("_", " ").title(), value) for key, value in payload.items())
    return 0


def cmd_report(args, store: ConfigStore) -> int:
    location = _root(args, store)
    libraries = list_libraries(location.path)
    text = environment_report(location.path, libraries, list_games(libraries))
    if args.output:
        output = Path(args.output).resolve(strict=False)
        if output.exists() and not args.force:
            raise FourUFourFreeError(f"Report already exists: {output}. Use --force to replace it.")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        AuditLog().record("report.created", {"output": str(output), "steam_root": str(location.path)})
        print(f"Report written: {output}")
    else:
        print(text)
    return 0


def cmd_audit(args, _store: ConfigStore) -> int:
    log = AuditLog(Path(args.audit_file) if args.audit_file else None)
    records = log.records(args.limit)
    if args.json:
        _json(records)
    else:
        for record in records:
            print(f"{record.get('time', '-')}  {record.get('event', '-')}  {json.dumps(record.get('details', {}), ensure_ascii=False)}")
    return 0


def cmd_config_show(args, store: ConfigStore) -> int:
    payload: Dict[str, object] = asdict(store.load())
    payload["config_file"] = str(store.path)
    _json(payload)
    return 0


def cmd_config_set(args, store: ConfigStore) -> int:
    if args.steam_root is None and args.preferred_library is None:
        raise FourUFourFreeError("Specify --steam-root and/or --preferred-library")
    config = store.load()
    if args.steam_root is not None:
        config.steam_root = str(Path(args.steam_root).expanduser().resolve(strict=False))
    if args.preferred_library is not None:
        config.preferred_library = str(Path(args.preferred_library).expanduser().resolve(strict=False))
    store.save(config)
    AuditLog().record("config.updated", {"config_file": str(store.path), "config": asdict(config)})
    print(f"Saved {store.path}")
    return 0


def cmd_config_export(args, store: ConfigStore) -> int:
    destination = export_config(store, Path(args.output), force=args.force)
    payload = {"output": str(destination), "config_file": str(store.path)}
    AuditLog().record("config.exported", payload)
    if args.json:
        _json(payload)
    else:
        print(f"Configuration exported: {destination}")
    return 0


def cmd_config_import(args, store: ConfigStore) -> int:
    result = import_config(store, Path(args.source), apply=args.apply)
    if result["applied"]:
        AuditLog().record(
            "config.imported",
            {
                "source": result["source"],
                "destination": result["destination"],
                "backup": result["backup"],
            },
        )
    if args.json:
        _json(result)
    elif result["applied"]:
        print(f"Configuration imported to {result['destination']}")
        if result["backup"]:
            print(f"Previous configuration: {result['backup']}")
    else:
        print("Configuration import verified. No settings were changed.")
        print("Run again with --apply to import it.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="4u4free",
        description="Transparent Steam library inspection, planning, and backup tools.",
    )
    parser.add_argument("--version", action="version", version=f"4u4free {__version__}")
    parser.add_argument("--debug", action="store_true", help="Show full tracebacks on unexpected errors")
    parser.add_argument("--config", type=Path, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def steam_options(command):
        command.add_argument("--steam-root", help="Explicit Steam installation root")
        command.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    doctor_parser = subparsers.add_parser("doctor", help="Check Python and Steam discovery")
    steam_options(doctor_parser)
    doctor_parser.set_defaults(handler=cmd_doctor)

    libraries_parser = subparsers.add_parser("libraries", help="List configured Steam libraries")
    steam_options(libraries_parser)
    libraries_parser.set_defaults(handler=cmd_libraries)

    games_parser = subparsers.add_parser("games", help="List installed games from ACF manifests")
    steam_options(games_parser)
    games_parser.set_defaults(handler=cmd_games)

    profiles_parser = subparsers.add_parser("profiles", help="List local Steam profiles and userdata roots")
    steam_options(profiles_parser)
    profiles_parser.set_defaults(handler=cmd_profiles)

    lua_parser = subparsers.add_parser("inspect-lua", help="Inspect a Lua metadata file without executing it")
    lua_parser.add_argument("path")
    lua_parser.add_argument("--show-secrets", action="store_true", help="Print depot keys and tokens; unsafe for shared logs")
    lua_parser.add_argument("--json", action="store_true")
    lua_parser.set_defaults(handler=cmd_inspect_lua)

    plan_parser = subparsers.add_parser("plan-import", help="Create a dry-run import plan")
    plan_parser.add_argument("path")
    steam_options(plan_parser)
    plan_parser.set_defaults(handler=cmd_plan_import)

    backup_parser = subparsers.add_parser("backup", help="Create a checksummed Steam-state backup")
    backup_parser.add_argument("--output", help="New destination directory")
    steam_options(backup_parser)
    backup_parser.set_defaults(handler=cmd_backup)

    verify_parser = subparsers.add_parser("verify-backup", help="Verify every file in a backup by SHA-256")
    verify_parser.add_argument("backup")
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(handler=cmd_verify_backup)

    restore_parser = subparsers.add_parser("restore", help="Verify and restore a backup; dry-run unless --apply is used")
    restore_parser.add_argument("backup")
    restore_parser.add_argument("--apply", action="store_true", help="Restore after creating an automatic pre-restore backup")
    steam_options(restore_parser)
    restore_parser.set_defaults(handler=cmd_restore)

    snapshot_parser = subparsers.add_parser("snapshot", help="Create or compare portable inventory snapshots")
    snapshot_subparsers = snapshot_parser.add_subparsers(dest="snapshot_command", required=True)
    snapshot_create = snapshot_subparsers.add_parser("create", help="Write the current Steam inventory to JSON")
    snapshot_create.add_argument("output")
    snapshot_create.add_argument("--force", action="store_true", help="Replace an existing snapshot")
    steam_options(snapshot_create)
    snapshot_create.set_defaults(handler=cmd_snapshot_create)
    snapshot_diff = snapshot_subparsers.add_parser("diff", help="Compare two inventory snapshot files")
    snapshot_diff.add_argument("before")
    snapshot_diff.add_argument("after")
    snapshot_diff.add_argument("--json", action="store_true")
    snapshot_diff.set_defaults(handler=cmd_snapshot_diff)

    managed_parser = subparsers.add_parser("managed-lua", help="Inspect or quarantine Steam plug-in Lua files")
    managed_subparsers = managed_parser.add_subparsers(dest="managed_command", required=True)
    managed_list = managed_subparsers.add_parser("list", help="List parsed plug-in Lua metadata with secrets redacted")
    steam_options(managed_list)
    managed_list.set_defaults(handler=cmd_managed_list)
    managed_quarantine = managed_subparsers.add_parser(
        "quarantine", help="Preview or quarantine plug-in Lua files for one App ID"
    )
    managed_quarantine.add_argument("app_id")
    managed_quarantine.add_argument("--apply", action="store_true", help="Back up Steam state and move matching files")
    managed_quarantine.add_argument("--quarantine", help="Override the quarantine parent directory")
    managed_quarantine.add_argument("--backup-output", help="Override the pre-change backup destination")
    steam_options(managed_quarantine)
    managed_quarantine.set_defaults(handler=cmd_managed_quarantine)

    scan_parser = subparsers.add_parser("scan", help="Index installed game manifests into the local catalog")
    scan_parser.add_argument("--catalog", help="Override the SQLite catalog path")
    steam_options(scan_parser)
    scan_parser.set_defaults(handler=cmd_scan)

    import_parser = subparsers.add_parser("import-lua", help="Parse and archive Lua metadata locally without installing it")
    import_parser.add_argument("path")
    import_parser.add_argument("--archive", help="Override the immutable archive directory")
    import_parser.add_argument("--catalog", help="Override the SQLite catalog path")
    import_parser.add_argument("--json", action="store_true")
    import_parser.set_defaults(handler=cmd_import_lua)

    catalog_parser = subparsers.add_parser("catalog", help="Query the local SQLite catalog")
    catalog_parser.add_argument("--catalog", help="Override the SQLite catalog path")
    catalog_subparsers = catalog_parser.add_subparsers(dest="catalog_command", required=True)
    catalog_games = catalog_subparsers.add_parser("games")
    catalog_games.add_argument("--query")
    catalog_games.add_argument("--json", action="store_true")
    catalog_games.set_defaults(handler=cmd_catalog_games)
    catalog_lua = catalog_subparsers.add_parser("lua")
    catalog_lua.add_argument("--app-id")
    catalog_lua.add_argument("--json", action="store_true")
    catalog_lua.set_defaults(handler=cmd_catalog_lua)
    catalog_stats = catalog_subparsers.add_parser("stats")
    catalog_stats.add_argument("--json", action="store_true")
    catalog_stats.set_defaults(handler=cmd_catalog_stats)

    report_parser = subparsers.add_parser("report", help="Create a local Steam environment report")
    report_parser.add_argument("--output")
    report_parser.add_argument("--force", action="store_true", help="Replace an existing report file")
    report_parser.add_argument("--steam-root", help="Explicit Steam installation root")
    report_parser.set_defaults(handler=cmd_report)

    audit_parser = subparsers.add_parser("audit", help="Show recent local write-operation audit events")
    audit_parser.add_argument("--audit-file")
    audit_parser.add_argument("--limit", type=int, default=50)
    audit_parser.add_argument("--json", action="store_true")
    audit_parser.set_defaults(handler=cmd_audit)

    config_parser = subparsers.add_parser("config", help="Show or update local configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_show = config_subparsers.add_parser("show")
    config_show.set_defaults(handler=cmd_config_show)
    config_set = config_subparsers.add_parser("set")
    config_set.add_argument("--steam-root")
    config_set.add_argument("--preferred-library")
    config_set.set_defaults(handler=cmd_config_set)
    config_export = config_subparsers.add_parser("export", help="Export validated non-secret settings")
    config_export.add_argument("output")
    config_export.add_argument("--force", action="store_true", help="Replace an existing export")
    config_export.add_argument("--json", action="store_true")
    config_export.set_defaults(handler=cmd_config_export)
    config_import = config_subparsers.add_parser("import", help="Validate or import a settings export")
    config_import.add_argument("source")
    config_import.add_argument("--apply", action="store_true", help="Back up current settings and import the export")
    config_import.add_argument("--json", action="store_true")
    config_import.set_defaults(handler=cmd_config_import)

    # SteaMidra integration commands
    dlc_parser = subparsers.add_parser("dlc-unlocker", help="Apply DLC unlockers (CreamAPI, SmokeAPI, Uplay R1/R2)")
    dlc_parser.add_argument("game_path", help="Path to the game folder")
    dlc_parser.add_argument("--unlocker", choices=["creamapi", "smokeapi", "uplay-r1", "uplay-r2"], help="Unlocker to apply")
    dlc_parser.add_argument("--app-id", type=int, help="Steam App ID (required for install)")
    dlc_parser.add_argument("--dlc-id", type=int, action="append", default=[], help="DLC App ID; repeatable")
    dlc_parser.add_argument("--list", action="store_true", help="List unlockers and whether each is installed")
    dlc_parser.add_argument("--validate", action="store_true", help="Show which platform DLLs exist in the game folder")
    dlc_parser.add_argument("--uninstall", action="store_true", help="Remove an installed unlocker and restore backups")
    dlc_parser.add_argument("--dry-run", action="store_true", help="Preview the install plan without changing files")
    dlc_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    steam_options(dlc_parser)
    dlc_parser.set_defaults(handler=cmd_dlc_unlocker)

    lc_parser = subparsers.add_parser("lumacore", help="Install or manage LumaCore (Steam ownership emulation)")
    lc_parser.add_argument("--install", action="store_true", help="Download and install LumaCore (default)")
    lc_parser.add_argument("--uninstall", action="store_true", help="Deactivate LumaCore and remove its DLLs")
    lc_parser.add_argument("--status", action="store_true", help="Check LumaCore installation status")
    lc_parser.add_argument("--check-update", action="store_true", help="Compare installed version against latest GitHub release")
    lc_parser.add_argument("--force", action="store_true", help="Bypass the update-check cache")
    steam_options(lc_parser)
    lc_parser.set_defaults(handler=cmd_lumacore)

    stub_parser = subparsers.add_parser("steamstub", help="Remove SteamStub DRM via Steamless")
    stub_parser.add_argument("game_path", help="Game folder (or single file with --file)")
    stub_parser.add_argument("--file", action="store_true", help="Treat game_path as a single executable")
    stub_parser.add_argument("--restore", action="store_true", help="Restore all .steamstub.bak backups in the folder")
    stub_parser.add_argument("--dry-run", action="store_true", help="List candidate executables without unpacking")
    stub_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    steam_options(stub_parser)
    stub_parser.set_defaults(handler=cmd_steamstub)

    crack_parser = subparsers.add_parser("crack", help="Search CrakFiles and apply a community fix to a game folder")
    crack_parser.add_argument("game_path", help="Target game folder")
    crack_parser.add_argument("--game-name", help="Game name to search for in the CrakFiles list")
    crack_parser.add_argument("--list", action="store_true", help="Only list matching games; no files are changed")
    crack_parser.add_argument("--dry-run", action="store_true", help="Preview without downloading or applying anything")
    steam_options(crack_parser)
    crack_parser.set_defaults(handler=cmd_crack)

    interactive_parser = subparsers.add_parser(
        "interactive", help="Start a friendly interactive shell over all commands"
    )
    interactive_parser.set_defaults(handler=cmd_interactive)

    return parser


def cmd_interactive(args, store: ConfigStore) -> int:
    """Friendly REPL over the same CLI commands. Type help for examples."""
    parser = build_parser()
    print("4u4free interactive shell — type 'help' for examples, 'quit' to exit.")
    while True:
        try:
            line = input("4u4free> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            return 0
        if line == "help":
            print(
                "Examples:\n"
                "  doctor\n"
                "  games\n"
                "  lumacore --status\n"
                "  dlc-unlocker \"C:\\Games\\MyGame\" --list\n"
                "  dlc-unlocker \"C:\\Games\\MyGame\" --validate\n"
                "  steamstub \"C:\\Games\\MyGame\" --dry-run\n"
                "  crack --game-name doom --list\n"
                "  <any other subcommand works too>"
            )
            continue
        try:
            parsed = parser.parse_args(shlex.split(line))
        except SystemExit:
            continue
        try:
            code = int(parsed.handler(parsed, store))
            if code:
                print(f"(exit code {code})")
        except FourUFourFreeError as exc:
            print(f"error: {exc}")
        except KeyboardInterrupt:
            print("\ninterrupted")
        except Exception as exc:
            if getattr(parsed, "debug", False):
                traceback.print_exc()
            else:
                print(f"unexpected error: {exc} (add --debug for details)")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = ConfigStore(getattr(args, "config", None))
    try:
        return int(args.handler(args, store))
    except FourUFourFreeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        if getattr(args, "debug", False):
            traceback.print_exc()
        else:
            print(f"unexpected error: {exc} — re-run with --debug for a full traceback", file=sys.stderr)
        return 1


def _require_sff() -> None:
    if not HAS_SFF:
        detail = f" ({SFF_IMPORT_ERROR})" if SFF_IMPORT_ERROR else ""
        raise FourUFourFreeError(f"SteaMidra features not available (sff package not importable){detail}")


def _confirm(prompt: str, assume_yes: bool = False) -> bool:
    """Ask before a destructive action. Non-interactive sessions must pass --yes."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise FourUFourFreeError(f"{prompt} Re-run with --yes to proceed non-interactively.")
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


_UNLOCKER_CACHE_DIR = Path.home() / ".4u4free" / "unlockers"

_UNLOCKER_KEYS = ("creamapi", "smokeapi", "uplay-r1", "uplay-r2")


def _make_downloader():
    return GitHubReleaseDownloader(_UNLOCKER_CACHE_DIR)


def _dll_dir_for(downloader, key: str):
    type_map = {
        "creamapi": UnlockerType.CREAMAPI,
        "smokeapi": UnlockerType.SMOKEAPI,
        "uplay-r1": UnlockerType.UPLAY_R1,
        "uplay-r2": UnlockerType.UPLAY_R2,
    }
    unlocker_type = type_map[key]
    return downloader.get_cached_dll(unlocker_type) or downloader._get_local_resource(unlocker_type)


def _log_to_stdout(message: str) -> None:
    print(message)


def cmd_dlc_unlocker(args, store: ConfigStore) -> int:
    _require_sff()
    game_path = Path(args.game_path).expanduser().resolve(strict=False)

    if args.list:
        instances = [
            ("creamapi", CreamAPIUnlocker()),
            ("smokeapi", SmokeAPIUnlocker()),
            ("uplay-r1", UplayR1Unlocker()),
            ("uplay-r2", UplayR2Unlocker()),
        ]
        payload = [
            {"unlocker": key, "display_name": inst.display_name,
             "installed": bool(game_path.exists() and game_path.is_dir() and inst.is_installed(game_path))}
            for key, inst in instances
        ]
        AuditLog().record("unlocker.listed", {"game": str(game_path)})
        if args.json:
            _json(payload)
        else:
            rows = [("UNLOCKER", "DISPLAY NAME", "INSTALLED")]
            rows.extend((entry["unlocker"], entry["display_name"], "yes" if entry["installed"] else "no") for entry in payload)
            _print_rows(rows)
        return 0

    valid, error = validate_game_directory(game_path)
    if not valid:
        raise FourUFourFreeError(error)

    if args.validate:
        payload = {
            "game_path": str(game_path),
            "steam_api32": (game_path / "steam_api.dll").exists(),
            "steam_api64": (game_path / "steam_api64.dll").exists(),
            "uplay_r1": (game_path / "uplay_r1_loader.dll").exists(),
            "uplay_r2": (game_path / "upc_r2_loader.dll").exists(),
        }
        if args.json:
            _json(payload)
        else:
            _print_rows((key.replace("_", " ").title(), value) for key, value in payload.items())
        return 0

    if not args.unlocker:
        raise FourUFourFreeError("Specify --unlocker (creamapi, smokeapi, uplay-r1, uplay-r2)")

    downloader = _make_downloader()

    if args.uninstall:
        if not _confirm(f"Uninstall {args.unlocker} from {game_path}?", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        uninstallers = {
            "creamapi": CreamAPIUnlocker(),
            "smokeapi": SmokeAPIUnlocker(),
            "uplay-r1": UplayR1Unlocker(),
            "uplay-r2": UplayR2Unlocker(),
        }
        ok = uninstallers[args.unlocker].uninstall(game_path)
        AuditLog().record("unlocker.uninstalled", {"game": str(game_path), "unlocker": args.unlocker, "ok": ok})
        if args.json:
            _json({"success": ok})
        print(f"{'Uninstalled' if ok else 'Failed to uninstall'} {args.unlocker}: {game_path}")
        return 0 if ok else 1

    if args.app_id is None:
        raise FourUFourFreeError("Specify --app-id when installing")
    valid, error = validate_app_id(args.app_id)
    if not valid:
        raise FourUFourFreeError(error)
    dlc_ids = [int(dlc) for dlc in (args.dlc_id or [])]
    valid, error = validate_dlc_ids(dlc_ids)
    if not valid:
        raise FourUFourFreeError(error)

    if args.dry_run:
        plan = {
            "action": "install",
            "unlocker": args.unlocker,
            "game_path": str(game_path),
            "app_id": args.app_id,
            "dlc_ids": dlc_ids,
            "already_installed": False,
        }
        try:
            plan["already_installed"] = {
                "creamapi": lambda: CreamAPIUnlocker().is_installed(game_path),
                "smokeapi": lambda: SmokeAPIUnlocker().is_installed(game_path),
                "uplay-r1": lambda: UplayR1Unlocker().is_installed(game_path),
                "uplay-r2": lambda: UplayR2Unlocker().is_installed(game_path),
            }[args.unlocker]()
        except Exception:
            pass
        if args.json:
            _json(plan)
        else:
            print("Dry-run plan:")
            for key, value in plan.items():
                print(f"  {key.replace('_', ' ').title()}: {value}")
        return 0

    if args.unlocker == "creamapi":
        if not _confirm(f"Install {args.unlocker} into {game_path}? Original DLLs are backed up.", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        ok = CreamAPIUnlocker(downloader).install(game_path, dlc_ids, args.app_id)
    elif args.unlocker == "smokeapi":
        if not _confirm(f"Install {args.unlocker} into {game_path}? Original DLLs are backed up.", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        ok = SmokeAPIUnlocker().install(game_path, dlc_ids, args.app_id, smokeapi_dir=_dll_dir_for(downloader, "smokeapi"))
    elif args.unlocker == "uplay-r1":
        if not _confirm(f"Install {args.unlocker} into {game_path}? Original DLLs are backed up.", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        ok = UplayR1Unlocker().install(game_path, dlc_ids, args.app_id, unlocker_dir=_dll_dir_for(downloader, "uplay-r1"))
    else:
        if not _confirm(f"Install {args.unlocker} into {game_path}? Original DLLs are backed up.", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        ok = UplayR2Unlocker().install(game_path, dlc_ids, args.app_id, unlocker_dir=_dll_dir_for(downloader, "uplay-r2"))

    AuditLog().record(
        "unlocker.installed",
        {"game": str(game_path), "unlocker": args.unlocker, "app_id": args.app_id, "dlc_ids": dlc_ids, "ok": ok},
    )
    if args.json:
        _json({"success": ok, "unlocker": args.unlocker, "app_id": args.app_id})
    print(f"{'Installed' if ok else 'Failed to install'} {args.unlocker} into {game_path}")
    return 0 if ok else 1


def cmd_lumacore(args, store: ConfigStore) -> int:
    _require_sff()
    location = _root(args, store)
    steam_path = location.path

    if args.status:
        version = get_installed_lumacore_version(steam_path)
        dlls = {dll: (steam_path / dll).is_file() for dll in ("dwmapi.dll", "xinput1_4.dll", "LumaCore.dll", "LumaCorePayload.dll")}
        payload = {"steam_root": str(steam_path), "version": version or None, "files": dlls}
        AuditLog().record("lumacore.status", payload)
        if args.json:
            _json(payload)
        else:
            print(f"Steam root: {steam_path}")
            print(f"LumaCore installed: {'yes' if version else 'no'}")
            if version:
                print(f"Version: {version}")
            for dll, present in dlls.items():
                print(f"  {dll}: {'present' if present else 'missing'}")
        return 0

    if args.check_update:
        update = check_for_lumacore_update(steam_path, force=args.force)
        if args.json:
            _json(update)
        else:
            print(f"Installed: {update['installed'] or '-'}")
            print(f"Latest: {update['latest'] or '-'}")
            print(f"Update available: {'yes' if update['update_available'] else 'no'}")
        return 0 if not update["update_available"] else 4

    if args.uninstall:
        ok, message = deactivate_lumacore(steam_path, progress_callback=_log_to_stdout)
        AuditLog().record("lumacore.deactivated", {"steam_root": str(steam_path), "ok": ok, "message": message})
        if args.json:
            _json({"success": ok, "message": message})
        elif not ok:
            print(message, file=sys.stderr)
        else:
            print(message)
        return 0 if ok else 1

    ok, message = install_lumacore(steam_path, progress_callback=_log_to_stdout)
    AuditLog().record("lumacore.installed", {"steam_root": str(steam_path), "ok": ok, "message": message})
    if args.json:
        _json({"success": ok, "message": message})
    elif not ok:
        print(message, file=sys.stderr)
    else:
        print(message)
    return 0 if ok else 1


def cmd_steamstub(args, store: ConfigStore) -> int:
    _require_sff()
    game_path = Path(args.game_path).expanduser().resolve(strict=False)
    unpacker = SteamStubUnpacker()

    if not unpacker.is_available():
        raise FourUFourFreeError("Steamless not found under third_party/. SteamStub removal unavailable.")

    if args.restore:
        if not _confirm(f"Restore all .steamstub.bak backups in {game_path}?", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        restored = unpacker.restore_directory(game_path, log_func=_log_to_stdout)
        AuditLog().record("steamstub.restored", {"path": str(game_path), "restored": restored})
        if args.json:
            _json({"restored": restored})
        return 0

    if args.file:
        target = game_path
        if not target.is_file():
            raise FourUFourFreeError(f"Not a file: {target}")
        if args.dry_run:
            print(f"Dry-run: would run Steamless on {target}")
            return 0
        if not _confirm(f"Run Steamless on {target}? A .steamstub.bak backup is created.", getattr(args, "yes", False)):
            print("Cancelled.")
            return 1
        ok = unpacker.unpack_file(str(target), log_func=_log_to_stdout)
        AuditLog().record("steamstub.unpacked", {"file": str(target), "ok": ok})
        if args.json:
            _json({"file": str(target), "unpacked": ok})
        return 0 if ok else 1

    if not game_path.is_dir():
        raise FourUFourFreeError(f"Directory not found: {game_path}")
    if args.dry_run:
        exe_files = [f for f in game_path.rglob("*.exe") if not unpacker._should_skip(f)]
        if args.json:
            _json({"candidates": [str(f) for f in exe_files]})
        else:
            print("Dry-run: executables eligible for SteamStub scan:")
            for exe in exe_files:
                print(f"  {exe}")
        return 0
    if not _confirm(f"Scan and unpack SteamStub executables under {game_path}?", getattr(args, "yes", False)):
        print("Cancelled.")
        return 1
    count = unpacker.unpack_directory(game_path, log_func=_log_to_stdout)
    AuditLog().record("steamstub.directory_unpacked", {"path": str(game_path), "count": count})
    if args.json:
        _json({"unpacked": count})
    return 0


def cmd_crack(args, store: ConfigStore) -> int:
    _require_sff()
    if args.list:
        games = fetch_crack_games()
        matches = search_crack_games(args.game_name or "", games) if args.game_name else games
        names = sorted({g.get("name", "?") for g in matches})
        if args.json:
            _json(names)
        else:
            for name in names:
                print(name)
        return 0

    game_folder = Path(args.game_path).expanduser().resolve(strict=False)
    if not game_folder.is_dir():
        raise FourUFourFreeError(f"Game folder not found: {game_folder}")

    if args.dry_run:
        print(f"Dry-run: would fetch CrakFiles list and apply the chosen fix to {game_folder}")
        return 0

    ok = apply_crack_fix(args.game_name, game_folder)
    AuditLog().record("crack.applied", {"folder": str(game_folder), "name": args.game_name, "ok": ok})
    if args.json:
        _json({"success": ok})
    return 0 if ok else 1
