@echo off
echo ==========================================
echo      Starting Build Process...
echo ==========================================

REM Install PyInstaller if missing (just in case)
pip install pyinstaller

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del *.spec

echo.
echo Building executable...
echo This may take a few minutes.
echo.

REM Build command
REM --windowed: No console window
REM --onedir: Create a directory (faster startup than onefile)
REM --name: Name of the exe
REM --clean: Clean cache
pyinstaller --noconfirm --windowed --clean --name "FanqieNovelDownloader" --collect-all PySide6 main.py

echo.
echo ==========================================
if exist "dist\FanqieNovelDownloader\FanqieNovelDownloader.exe" (
    echo Build SUCCESS!
    echo The application is located in: dist\FanqieNovelDownloader
    echo You can zip this folder and distribute it to other Windows users.
) else (
    echo Build FAILED! Please check the error messages above.
)
echo ==========================================
pause
