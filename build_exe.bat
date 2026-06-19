@echo off
setlocal
cd /d "%~dp0"

echo === DXF SkyView: сборка exe ===
echo.

python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

python scripts\build_exe.py
if errorlevel 1 goto :error

echo.
pause
exit /b 0

:error
echo.
echo Сборка не удалась.
pause
exit /b 1
