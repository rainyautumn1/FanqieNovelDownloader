#!/bin/bash
echo "=========================================="
echo "     Starting Build Process (macOS)..."
echo "=========================================="

# Install PyInstaller if missing
pip install pyinstaller

# Clean previous builds
rm -rf build dist *.spec

echo ""
echo "Building executable..."
echo "This may take a few minutes."
echo ""

ICON_PARAM=""
ADD_DATA_PARAM=""
if [ -f "app.icns" ]; then
    echo "Found app.icns, enabling icon..."
    ICON_PARAM='--icon="app.icns"'
    ADD_DATA_PARAM='--add-data "app.icns:."'
fi

# Build command
pyinstaller --noconfirm --windowed --clean --name "FanqieNovelDownloader" $ICON_PARAM $ADD_DATA_PARAM --collect-all PySide6 main.py

echo ""
echo "Cleaning up source files from distribution..."
cd dist/FanqieNovelDownloader/_internal
rm -f download_manager.py download_ui.py downloader.py logging_config.py main.py ui_components.py update_manager.py version.py workers.py
cd ../../..

echo ""
echo "=========================================="
if [ -d "dist/FanqieNovelDownloader.app" ] || [ -f "dist/FanqieNovelDownloader/FanqieNovelDownloader" ]; then
    echo "Build SUCCESS!"
    echo "The application is located in: dist/FanqieNovelDownloader"
    echo "You can zip this folder and distribute it to macOS users."
else
    echo "Build FAILED! Please check the error messages above."
fi
echo "=========================================="
