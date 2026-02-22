@echo off
setlocal

set BUILD_TYPE=Release
set INSTALL_DIR=%~dp0install

if /i "%~1"=="debug" (
    set BUILD_TYPE=Debug
    set INSTALL_DIR=%~dp0install_debug
)

echo [1/4] Configuring CMake ...
cmake -B build -A x64 -DCMAKE_INSTALL_PREFIX="%INSTALL_DIR%"
if errorlevel 1 goto :fail

echo [2/4] Building (%BUILD_TYPE%) ...
cmake --build build --config %BUILD_TYPE%
if errorlevel 1 goto :fail

echo [3/4] Installing to %INSTALL_DIR% ...
cmake --install build --config %BUILD_TYPE%
if errorlevel 1 goto :fail

echo [4/4] Installing Python dependencies ...
pip install -r requirements.txt
if errorlevel 1 (
    echo WARNING: pip install failed, please run manually: pip install -r requirements.txt
)

echo.
echo ========================================
echo   %BUILD_TYPE% build complete!
echo   Install directory: %INSTALL_DIR%
echo   Run: python "%INSTALL_DIR%\dupfinder_ui.py"
echo ========================================
goto :eof

:fail
echo.
echo BUILD FAILED
exit /b 1
