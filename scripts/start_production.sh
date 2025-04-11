#!/bin/bash

# Production startup script for TabibMeet backend

# Check if conda is available and should be used
if command -v conda &> /dev/null; then
    # Source conda.sh to enable conda activation
    source "$(conda info --base)/etc/profile.d/conda.sh"
    
    # If CONDA_ENV is set, use that specific environment
    if [ -n "$CONDA_ENV" ]; then
        echo "Activating conda environment: $CONDA_ENV"
        conda activate $CONDA_ENV
        if [ $? -ne 0 ]; then
            echo "Failed to activate conda environment: $CONDA_ENV"
            exit 1
        fi
        echo "Conda environment '$CONDA_ENV' activated successfully"
    else
        # If no specific environment is set, use the base environment
        echo "No specific conda environment set, using base environment"
        conda activate base
        echo "Conda base environment activated"
    fi
# Otherwise, use traditional virtual environment if it exists
elif [ -d "venv" ] || [ -d "../venv" ]; then
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        source ../venv/bin/activate
    fi
    echo "Virtual environment activated"
fi

# Set environment variables
export PYTHONPATH=$(pwd)

# Install required dependencies using the dedicated script
echo "Installing/updating dependencies..."
bash scripts/install_dependencies.sh

# Check if gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo "Gunicorn not found. Attempting to install..."
    pip install gunicorn uvicorn
    
    # Check if installation was successful
    if ! command -v gunicorn &> /dev/null; then
        echo "ERROR: Failed to install gunicorn. Please install it manually with: pip install gunicorn uvicorn"
        exit 1
    fi
    echo "Gunicorn successfully installed"
fi

# Verify environment variables
echo "Verifying environment variables..."
python scripts/verify_env.py
if [ $? -ne 0 ]; then
    echo "ERROR: Environment validation failed. Please check your .env file."
    exit 1
fi

# Check if we need to run database migrations
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    # Replace with your actual migration command if using Alembic
    # alembic upgrade head
fi

# Start Gunicorn with our configuration
echo "Starting TabibMeet backend in production mode..."
exec gunicorn -c gunicorn_conf.py main:app
