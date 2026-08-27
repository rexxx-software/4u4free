# Release guide

4u4free releases are built from version tags by `.github/workflows/release.yml`.
The workflow publishes the Windows installer and a SHA-256 checksum file.

## Repository settings

Use these values on the GitHub repository page:

- **Description:** Desktop and CLI tools for inspecting, backing up, and managing local Steam libraries.
- **Topics:** `steam`, `steam-library`, `backup`, `python`, `pyside6`, `desktop-app`, `cli`, `vdf`, `game-library`
- **Features:** Issues and Discussions enabled; Wiki and Projects optional.
- **Security:** Enable private vulnerability reporting.
- **Default branch:** `main`

Protect `main` after the first push. Require the `test` workflow, block force
pushes, and require pull requests for changes from collaborators. The release
workflow uses GitHub's built-in token and does not require project secrets.

## Prepare a release

1. Update the version in `pyproject.toml` and `four_u_four_free/__init__.py`.
2. Update the version badge in `README.md`.
3. Add the release summary to `CHANGELOG.md`.
4. Run the local checks:

   ```powershell
   ruff check four_u_four_free tests
   pytest -q
   python -m build
   ```

5. Commit the release changes.
6. Create and push an annotated tag that exactly matches the package version:

   ```powershell
   git tag -a v0.5.2 -m "4u4free 0.5.2"
   git push origin main --follow-tags
   ```

The workflow rejects a tag whose version does not match both Python version
files. After the build completes, download the release assets, verify the
checksum, and install the Windows package on a clean system before announcing
the release.

## Local Windows build

With Python 3.12, a .NET SDK, PyInstaller, and NSIS 3 installed:

```powershell
python -m pip install -e ".[dev,gui]" pyinstaller build
.\build_installer.bat
```

The application bundle and installer are written to `dist\`.
