# Installing dependencies

Use a virtual environment so 4u4free does not change packages used by other
Python projects.

## Desktop application

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[gui]"
```

Start the application with `4u4free-gui` or run a diagnostic with
`4u4free doctor`.

## CLI only

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
4u4free doctor
```

## Development tools

```powershell
python -m pip install -e ".[dev,gui]"
ruff check four_u_four_free tests
pytest -q
```

## Full integrated compatibility layer

Some inherited SteaMidra modules have dependencies beyond the main 4u4free
desktop application. Install the complete pinned set only when working on those
modules or the legacy entry points:

```powershell
python -m pip install -r requirements.txt
python -m pip install steam==1.4.4 --no-deps
```

The second command avoids the Steam package's outdated transitive dependency
constraint while retaining the version used by the project.

## Windows release build

Release builds also require a .NET SDK, PyInstaller, and NSIS 3:

```powershell
python -m pip install -e ".[dev,gui]" pyinstaller build
.\build_installer.bat
```

See [`docs/RELEASING.md`](docs/RELEASING.md) for artifact names and the tagged
release process.
