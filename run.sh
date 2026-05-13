#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies. Please check your python environment."
    exit 1
fi

echo "Starting Fanqie Downloader..."
python main.py
