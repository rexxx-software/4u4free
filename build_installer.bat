@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_EXE=python"
for /f "usebackq delims=" %%V in (`%PYTHON_EXE% -c "from four_u_four_free import __version__; print(__version__)"`) do set "APP_VERSION=%%V"
for /f "usebackq delims=" %%V in (`%PYTHON_EXE% -c "from four_u_four_free import __version__; v=__version__.split('.'); print('.'.join((v+['0','0','0','0'])[:4]))"`) do set "APP_VERSION4=%%V"

if not defined APP_VERSION (
    echo Could not read the application version from pyproject.toml.
    exit /b 1
)

echo Building 4u4free %APP_VERSION%

if /i "%~1"=="installer-only" goto prepare_installer

echo [1/2] Building the application bundle...
call build_4u4free_gui.bat
if errorlevel 1 exit /b %errorlevel%

:prepare_installer
if not exist "dist\4u4free\4u4free.exe" (
    echo Application bundle not found. Run this script without installer-only first.
    exit /b 1
)

set "MAKENSIS_EXE="
if defined NSIS if exist "%NSIS%" set "MAKENSIS_EXE=%NSIS%"
if not defined MAKENSIS_EXE if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set "MAKENSIS_EXE=%ProgramFiles(x86)%\NSIS\makensis.exe"
if not defined MAKENSIS_EXE if exist "%ProgramFiles%\NSIS\makensis.exe" set "MAKENSIS_EXE=%ProgramFiles%\NSIS\makensis.exe"
if not defined MAKENSIS_EXE if exist "%LOCALAPPDATA%\4u4free-build-tools\nsis-3.12\makensis.exe" set "MAKENSIS_EXE=%LOCALAPPDATA%\4u4free-build-tools\nsis-3.12\makensis.exe"
if not defined MAKENSIS_EXE if exist "%LOCALAPPDATA%\4u4free-build-tools\nsis-3.11\nsis-3.11\Bin\makensis.exe" set "MAKENSIS_EXE=%LOCALAPPDATA%\4u4free-build-tools\nsis-3.11\nsis-3.11\Bin\makensis.exe"
if not defined MAKENSIS_EXE for /f "delims=" %%P in ('where makensis.exe 2^>nul') do if not defined MAKENSIS_EXE set "MAKENSIS_EXE=%%P"

if not defined MAKENSIS_EXE (
    echo NSIS was not found. Install NSIS 3 from https://nsis.sourceforge.io/Download
    exit /b 1
)

echo [2/2] Compiling the installer...
if exist "dist\4u4free-%APP_VERSION%-Setup.exe" del /f /q "dist\4u4free-%APP_VERSION%-Setup.exe"
if exist "dist\4u4free-%APP_VERSION%-Setup.exe" (
    echo Existing installer could not be replaced. Close it and try again.
    exit /b 1
)
"%MAKENSIS_EXE%" /DVERSION=%APP_VERSION% /DVERSION4=%APP_VERSION4% installer.nsi
if errorlevel 1 exit /b %errorlevel%

echo.
echo Installer created: dist\4u4free-%APP_VERSION%-Setup.exe
exit /b 0
