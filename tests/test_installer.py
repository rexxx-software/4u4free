import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_has_expected_user_options() -> None:
    script = (ROOT / "installer.nsi").read_text(encoding="utf-8")

    assert 'InstallDir "$PROGRAMFILES64\\${APP_NAME}"' in script
    assert "!insertmacro MUI_PAGE_DIRECTORY" in script
    assert "!insertmacro MUI_PAGE_STARTMENU" in script
    assert 'Section "Desktop shortcut"' in script
    assert 'WriteUninstaller "$INSTDIR\\Uninstall.exe"' in script
    assert 'WriteRegStr HKLM "${APP_UNINSTALL_KEY}"' in script
    assert "!define MUI_FINISHPAGE_RUN" in script


def test_installer_excludes_legacy_settings_artifact() -> None:
    script = (ROOT / "installer.nsi").read_text(encoding="utf-8")

    assert 'File /r /x "settings.bin"' in script


def test_playtime_helper_matches_published_checksum() -> None:
    helper_dir = ROOT / "third_party" / "steam-achievement-manager"
    expected = {
        line.split(maxsplit=1)[1]: line.split(maxsplit=1)[0]
        for line in (helper_dir / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    helper = helper_dir / "4u4free.PlaytimeIdler.exe"

    assert hashlib.sha256(helper.read_bytes()).hexdigest() == expected[helper.name]


def test_release_checksum_does_not_hash_itself() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "! -name SHA256SUMS.txt" in workflow
