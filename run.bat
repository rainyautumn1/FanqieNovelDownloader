@echo off
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies. Please check your python environment.
    pause
    exit /b
)

echo Starting Fanqie Downloader...
python main.py
pause
