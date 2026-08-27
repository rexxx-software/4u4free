"""Build a dependency-free 4u4free.pyz archive."""

from __future__ import annotations

import shutil
import zipapp
from pathlib import Path


def main() -> int:
    project = Path(__file__).resolve().parent.parent
    output_dir = project / "dist"
    stage = output_dir / ".zipapp-build"
    output = output_dir / "4u4free.pyz"
    output_dir.mkdir(exist_ok=True)

    if stage.exists():
        resolved = stage.resolve()
        if resolved.parent != output_dir.resolve() or resolved.name != ".zipapp-build":
            raise RuntimeError(f"Unsafe staging path: {resolved}")
        shutil.rmtree(stage)
    stage.mkdir()
    try:
        shutil.copytree(
            project / "four_u_four_free",
            stage / "four_u_four_free",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        for name in ("LICENSE", "ATTRIBUTION.md"):
            source = project / name
            if source.is_file():
                shutil.copy2(source, stage / name)
        zipapp.create_archive(
            stage,
            target=output,
            interpreter="/usr/bin/env python3",
            main="four_u_four_free.cli:main",
            compressed=True,
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
