@echo off
setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

set RELEASE_NAME=dupfinder-windows-x64
set DIST_DIR=%SCRIPT_DIR%dist
set OUT_DIR=%DIST_DIR%\%RELEASE_NAME%
set CMAKE_BUILD=%SCRIPT_DIR%cmake-build

echo ============================================
echo   DupFinder Release Packager (Windows)
echo ============================================

REM --- Step 1: Build C++ engine ---
echo.
echo [1/4] Building C++ engine ...
cmake -B "%CMAKE_BUILD%" -A x64
if errorlevel 1 goto :fail
cmake --build "%CMAKE_BUILD%" --config Release
if errorlevel 1 goto :fail

REM --- Step 2: Ensure venv with dependencies ---
echo.
echo [2/4] Preparing Python environment ...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -q pyinstaller -r requirements.txt
if errorlevel 1 (
    echo WARNING: pip install had issues
)

REM --- Step 3: PyInstaller bundle ---
echo.
echo [3/4] Packaging with PyInstaller ...
pyinstaller ^
    --noconfirm ^
    --clean ^
    --name dupfinder ^
    --windowed ^
    --onefile ^
    --add-data "dupfinder_strings.json;." ^
    --add-data "font;font" ^
    --collect-all ttkthemes ^
    --collect-all sv_ttk ^
    --hidden-import send2trash ^
    --hidden-import PIL ^
    dupfinder_ui.py
if errorlevel 1 goto :fail

REM --- Step 4: Assemble release ---
echo.
echo [4/4] Assembling release package ...
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
mkdir "%OUT_DIR%"

copy /y "%DIST_DIR%\dupfinder.exe" "%OUT_DIR%\"
copy /y "%CMAKE_BUILD%\Release\dupfinder_engine.exe" "%OUT_DIR%\dupfinder_engine.exe"

REM Clean up intermediate files
del /q "%DIST_DIR%\dupfinder.exe" 2>nul

echo.
echo ============================================
echo   Release package created:
echo   %OUT_DIR%
echo   Contents: dupfinder.exe + dupfinder_engine.exe
echo   Zip this folder for distribution.
echo ============================================
goto :eof

:fail
echo.
echo PACKAGING FAILED
exit /b 1
