#!/bin/bash

# This script runs the FastAPI application with a clean environment
# so that only .env file values are used

echo "Running with clean environment..."
echo "Clearing all environment variables and using only .env values"

# Run the Python app with a clean environment, passing only PATH
env -i PATH=$PATH python main.py
