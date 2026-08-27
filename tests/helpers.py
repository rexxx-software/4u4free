from pathlib import Path


def make_fake_steam(root: Path) -> tuple[Path, Path]:
    steam = root / "Steam"
    second = root / "Library Two"
    (steam / "config" / "stplug-in").mkdir(parents=True)
    (steam / "steamapps").mkdir(parents=True)
    (second / "steamapps").mkdir(parents=True)
    (steam / "config" / "config.vdf").write_text('"InstallConfigStore"\n{\n}\n', encoding="utf-8")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'''"libraryfolders"
{{
    "0" {{ "path" "{str(steam).replace(chr(92), chr(92) * 2)}" }}
    "1" {{ "path" "{str(second).replace(chr(92), chr(92) * 2)}" }}
}}
''',
        encoding="utf-8",
    )
    (steam / "steamapps" / "appmanifest_10.acf").write_text(
        '''"AppState"
{
    "appid" "10"
    "name" "Counter-Strike"
    "installdir" "Half-Life"
    "buildid" "123"
    "LastUpdated" "456"
}
''',
        encoding="utf-8",
    )
    (second / "steamapps" / "appmanifest_20.acf").write_text(
        '''"AppState" { "appid" "20" "name" "Team Fortress Classic" "buildid" "789" }''',
        encoding="utf-8",
    )
    (steam / "config" / "stplug-in" / "10.lua").write_text("addappid(10)\n", encoding="utf-8")
    return steam, second

