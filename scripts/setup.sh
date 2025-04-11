#!/bin/bash

echo "Setting up TabibMeet Backend environment..."

# Activate virtual environment if it exists
if [ -d "venv" ] || [ -d "../venv" ]; then
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        source ../venv/bin/activate
    fi
    echo "Virtual environment activated"
else
    echo "Creating virtual environment..."
    python -m venv venv
    source venv/bin/activate
fi

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete!"
echo "To start the development server, run: python main.py"
echo "To start the production server, run: bash scripts/start_production.sh"
