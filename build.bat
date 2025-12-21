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

set ICON_PARAM=
set ADD_DATA_PARAM=
if exist app.ico (
    echo Found app.ico, enabling icon...
    set ICON_PARAM=--icon="app.ico"
    set ADD_DATA_PARAM=--add-data "app.ico;."
)

REM Build command
REM --windowed: No console window
REM --onedir: Create a directory (faster startup than onefile)
REM --name: Name of the exe
REM --clean: Clean cache
pyinstaller --noconfirm --windowed --clean --name "FanqieNovelDownloader" %ICON_PARAM% %ADD_DATA_PARAM% --collect-all PySide6 main.py

echo.
echo Cleaning up source files from distribution...
cd dist\FanqieNovelDownloader\_internal
if exist download_manager.py del download_manager.py
if exist download_ui.py del download_ui.py
if exist downloader.py del downloader.py
if exist logging_config.py del logging_config.py
if exist main.py del main.py
if exist ui_components.py del ui_components.py
if exist update_manager.py del update_manager.py
if exist version.py del version.py
if exist workers.py del workers.py
cd ..\..\..

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
