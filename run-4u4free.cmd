@echo off
setlocal
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%~dp04u4free.py" %*
    exit /b %ERRORLEVEL%
)
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%~dp04u4free.py" %*
    exit /b %ERRORLEVEL%
)
echo 4u4free requires Python 3.10 or newer. 1>&2
exit /b 1

