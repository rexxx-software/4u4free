<p align="center">
  <img src="four_u_four_free/assets/brand-mark.png" alt="4u4free logo" width="112">
</p>

<h1 align="center">4u4free</h1>

<p align="center">
  A desktop and command-line toolkit for inspecting, backing up, and managing local Steam libraries.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.4-6c63ff">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
  <img alt="License" src="https://img.shields.io/badge/license-GPL--3.0--or--later-2ea44f">
  <img alt="Platform" src="https://img.shields.io/badge/desktop-Windows-0078d4">
  <a href="https://github.com/rexxx-software/4u4free/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/rexxx-software/4u4free/actions/workflows/ci.yml/badge.svg"></a>
</p>

**Developed and maintained by rexxx.**

4u4free brings Steam library discovery, local metadata inspection, verified backups, save management, and compatibility tools into one interface. It includes a native desktop application for everyday use and a scriptable CLI for diagnostics, reports, and repeatable maintenance.

## Features

| Area | Capabilities |
| --- | --- |
| Library overview | Detect Steam installations and library folders, list installed games, inspect local profiles, and index game metadata in SQLite. |
| Desktop interface | Searchable game library, Store and Downloads views, DLC tools, Save Vault, activity history, and configurable paths and appearance. |
| Backup and recovery | Create allowlisted backups, verify every file with SHA-256, preview restores, and take a safety snapshot before applying changes. |
| Portable snapshots | Export a versioned JSON inventory and compare snapshots to find added, removed, or changed games. |
| Lua inspection | Parse supported Steam metadata directives without executing Lua, redact sensitive values by default, and archive imports by content hash. |
| Save Vault | Create per-game ZIP snapshots, verify archives before restore, and preserve the current destination before overwriting files. |
| Local integrations | Achievement and stat management, playtime sessions, LumaCore status and setup, DLC unlocker management, SteamStub maintenance, and compatibility checks. |
| Automation | Machine-readable JSON output, a local write-operation audit log, dry-run support, and a guided interactive shell. |

4u4free does not ask for or store Steam credentials. Features that use Steam operate through the client session already running on the computer.

## Requirements

### Desktop application

- Windows 10 or Windows 11, 64-bit
- Steam installed for library-management features
- The latest [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

### Running from source

- Python 3.10 or newer
- Git
- A .NET SDK for the playtime helper used by packaged Windows builds
- NSIS 3 only when building the Windows installer

## Install

### Windows release

Download the latest Windows installer from [Releases](../../releases/latest). It adds Start menu shortcuts and a standard Windows uninstaller.

### Run from source on Windows

```powershell
git clone https://github.com/rexxx-software/4u4free.git
cd 4u4free
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[gui]"
4u4free doctor
4u4free-gui
```

If PowerShell blocks local activation scripts, use `.\.venv\Scripts\python.exe -m pip` and `.\.venv\Scripts\4u4free-gui.exe` directly.

### Run the CLI on Linux or macOS

```bash
git clone https://github.com/rexxx-software/4u4free.git
cd 4u4free
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
4u4free doctor
```

The inspection, catalog, backup, snapshot, and reporting commands are designed to be portable. Windows-specific Steam integrations are unavailable on other platforms.

## Common commands

```text
4u4free doctor                         Check Python and Steam discovery
4u4free libraries                      List registered Steam libraries
4u4free games                          List installed games
4u4free profiles                       List local Steam profiles
4u4free backup                         Create a checksummed Steam-state backup
4u4free verify-backup <folder>         Verify a backup before use
4u4free snapshot create inventory.json Export a portable library inventory
4u4free snapshot diff old.json new.json
4u4free report                         Generate a local environment report
4u4free interactive                    Open the guided command shell
```

Add `--json` to supported commands for machine-readable output. Commands that can alter files provide a preview or confirmation step; scriptable operations expose explicit flags such as `--apply`, `--dry-run`, or `--yes`.

The full CLI reference is in [docs/COMMAND_REFERENCE.md](docs/COMMAND_REFERENCE.md).

## Build the Windows release

Install the development dependencies, PyInstaller, a .NET SDK, and NSIS 3, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,gui]" pyinstaller
.\build_installer.bat
```

Build output is written to `dist\`:

- `dist\4u4free-<version>-Setup.exe` - Windows installer

The local build also creates an intermediate application directory used to assemble the installer. Tagged releases are built automatically by GitHub Actions and publish only the installer plus its SHA-256 checksum. See [docs/RELEASING.md](docs/RELEASING.md) for the complete release checklist.

## Project layout

```text
four_u_four_free/          Main package, desktop interface, and internal compatibility support
third_party/               Audited runtime components included with the Windows installer
tools/                     Build helpers and the playtime helper source
tests/                     Automated test suite
docs/                      Command reference and release guide
.github/workflows/         Continuous integration and installer release automation
```

## Development

```powershell
python -m pip install -e ".[dev,gui]"
ruff check four_u_four_free tests
pytest -q
```

Bug reports and focused pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Security issues should follow the private reporting process in [SECURITY.md](SECURITY.md).

## Authorship and third-party work

4u4free is developed and maintained by **rexxx**. A limited internal compatibility layer contains adapted open-source work whose original authors retain copyright. Exact sources, versions, and bundled component licenses are documented in [ATTRIBUTION.md](ATTRIBUTION.md).

## License

4u4free source code is released under the [GNU General Public License v3.0 or later](LICENSE). Bundled third-party components remain under their respective licenses.

## Responsible use

Use 4u4free only with software and accounts you own or are authorized to manage. Some compatibility features modify local Steam or game files and may affect support eligibility, online access, or platform terms. Review each operation, keep backups, and understand the applicable license and service rules before making changes.
