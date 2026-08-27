"""Generate PyInstaller version metadata from the package version."""

from pathlib import Path
import re


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    init_text = (root / "four_u_four_free" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', init_text, re.MULTILINE)
    if not match:
        raise SystemExit("Could not read the 4u4free package version")
    version = match.group(1)
    parts = [int(part) for part in version.split(".")]
    version_tuple = tuple((parts + [0, 0, 0, 0])[:4])
    comma_version = ", ".join(str(part) for part in version_tuple)
    destination = root / "build" / "windows_version_info.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({comma_version}),
    prodvers=({comma_version}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'rexxx'),
          StringStruct(u'FileDescription', u'4u4free desktop application'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'InternalName', u'4u4free'),
          StringStruct(u'LegalCopyright', u'Copyright (c) 2026 rexxx'),
          StringStruct(u'OriginalFilename', u'4u4free.exe'),
          StringStruct(u'ProductName', u'4u4free'),
          StringStruct(u'ProductVersion', u'{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    print(f"Wrote {destination} for 4u4free {version}")


if __name__ == "__main__":
    main()
