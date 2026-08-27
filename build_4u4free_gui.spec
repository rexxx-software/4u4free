# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

import PySide6
from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH)


def bundled(source: str, destination: str):
    path = ROOT / source
    return (str(path), destination) if path.exists() else None


datas = [
    bundled("four_u_four_free/assets", "four_u_four_free/assets"),
    bundled(
        "four_u_four_free/data/store_metadata",
        "four_u_four_free/data/store_metadata",
    ),
    bundled("four_u_four_free/data/all_games.txt", "four_u_four_free/data"),
    bundled("four_u_four_free/_compat/lua/fallback_depotkeys.json", "four_u_four_free/_compat/lua"),
    bundled("four_u_four_free/_compat/dlc_unlockers/resources", "four_u_four_free/_compat/dlc_unlockers/resources"),
    bundled("third_party/steamless", "third_party/steamless"),
    bundled(
        "third_party/steam-achievement-manager",
        "third_party/steam-achievement-manager",
    ),
    bundled(
        "third_party/steamdb-file-detection",
        "third_party/steamdb-file-detection",
    ),
]
datas = [item for item in datas if item is not None]

hiddenimports = (
    collect_submodules("four_u_four_free._compat.dlc_unlockers")
    + [
        "eventemitter",
        "gevent",
        "gevent.monkey",
        "vdf",
    ]
)

a = Analysis(
    [str(ROOT / "4u4free_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "Crypto",
        "PIL",
        "_pytest",
        "cryptography",
        "lxml",
        "matplotlib",
        "numpy",
        "pandas",
        "py",
        "pygments",
        "pytest",
        "rich",
        "sqlalchemy",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)

# Python 3.10 on this build host ships the VS 2019 runtime, while current
# PySide6 wheels are linked against a newer VS 2022 runtime. PyInstaller puts
# Python's copies at the DLL search root, where they otherwise shadow Qt's
# compatible copies and make QtCore fail with ERROR_PROC_NOT_FOUND.
qt_runtime_dir = Path(PySide6.__file__).resolve().parent
qt_runtime_names = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
}

# Qt 6 on Windows uses the operating system's ICU library. A developer tool on
# PATH can make PyInstaller pick up an unrelated icuuc.dll and its data DLL;
# those files then shadow the Windows copy and QtCore fails with WinError 127.
def is_foreign_icu(entry):
    destination = Path(entry[0])
    name = destination.name.casefold()
    return len(destination.parts) == 1 and (
        name == "icuuc.dll" or (name.startswith("icudt") and name.endswith(".dll"))
    )


a.binaries = [
    entry
    for entry in a.binaries
    if not is_foreign_icu(entry)
    and not (
        len(Path(entry[0]).parts) == 1
        and Path(entry[0]).name.casefold() in qt_runtime_names
    )
]
for runtime_name in sorted(qt_runtime_names):
    runtime_path = qt_runtime_dir / runtime_name.upper()
    if runtime_path.is_file():
        a.binaries.append((runtime_name.upper(), str(runtime_path), "BINARY"))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="4u4free",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "four_u_four_free" / "assets" / "4u4free.ico"),
    version=str(ROOT / "build" / "windows_version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="4u4free",
)
