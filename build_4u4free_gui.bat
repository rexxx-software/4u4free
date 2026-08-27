@echo off
setlocal
cd /d "%~dp0"
dotnet build tools\playtime_idler\4u4free.PlaytimeIdler.csproj -c Release -p:Platform=x86 --nologo
if errorlevel 1 exit /b %errorlevel%
python tools\write_windows_version_info.py
if errorlevel 1 exit /b %errorlevel%
python -m PyInstaller --noconfirm --clean build_4u4free_gui.spec
if errorlevel 1 exit /b %errorlevel%
echo Built dist\4u4free\4u4free.exe
