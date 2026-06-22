@echo off
setlocal
cd /d "%~dp0"

echo === DXF SkyView: релиз (ветка + установщик + GitHub) ===
echo.

python -m pip install -q -r requirements-build.txt
if errorlevel 1 goto :error

python scripts\release.py %*
if errorlevel 1 goto :error

echo.
pause
exit /b 0

:error
echo.
echo Релиз не удался.
pause
exit /b 1
