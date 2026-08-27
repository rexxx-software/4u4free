@echo off
setlocal
pushd "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -m unittest discover -s tests -v
    set TEST_RESULT=%ERRORLEVEL%
    popd
    exit /b %TEST_RESULT%
)
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python -m unittest discover -s tests -v
    set TEST_RESULT=%ERRORLEVEL%
    popd
    exit /b %TEST_RESULT%
)
popd
echo 4u4free tests require Python 3.10 or newer. 1>&2
exit /b 1
