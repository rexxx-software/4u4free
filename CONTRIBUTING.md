# Contributing to 4u4free

Bug fixes, documentation improvements, platform fixes, and focused feature
work are welcome.

## Development setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,gui]"
```

Run the checks before opening a pull request:

```powershell
ruff check four_u_four_free tests
pytest -q
```

## Pull requests

- Keep each pull request focused on one change.
- Add or update tests when behavior changes.
- Preserve dry-run, confirmation, backup, and audit behavior for file-changing operations.
- Do not commit credentials, account data, local settings, logs, build output, or downloaded archives.
- Record the source and license of any new third-party file or dependency.
- Update the README or command reference when user-facing behavior changes.

By submitting a contribution, you agree that it may be distributed under the
project's GPL-3.0-or-later license. Third-party files must remain under licenses
that permit their inclusion and intended use.
