#!/bin/bash

# Setup script for TabibMeet backend conda environment

# Environment name (change as needed)
ENV_NAME="tabibmeet"

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    echo "Conda is not installed. Please install Conda first."
    exit 1
fi

# Create conda environment if it doesn't exist
if ! conda env list | grep -q "^$ENV_NAME "; then
    echo "Creating conda environment '$ENV_NAME'..."
    conda create -y -n $ENV_NAME python=3.10
else
    echo "Conda environment '$ENV_NAME' already exists."
fi

# Activate conda environment
echo "Activating conda environment '$ENV_NAME'..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate $ENV_NAME

# Clean existing installations to avoid conflicts
pip uninstall -y fastapi pydantic pydantic-settings

# Install key dependencies with compatible versions first
pip install "fastapi>=0.100.0" "pydantic>=2.0.0" "pydantic-settings>=2.0.0"

# Install pip packages from requirements.txt
echo "Installing remaining dependencies from requirements.txt..."
pip install -r ../requirements.txt

# Check for any dependency conflicts
echo "Checking for dependency conflicts..."
pip check

if [ $? -eq 0 ]; then
    echo "All dependencies installed successfully with no conflicts."
else
    echo "Warning: There may be dependency conflicts. Please review the output above."
    echo "Installed versions of key packages:"
    pip show fastapi pydantic pydantic-settings | grep -E "Name|Version"
fi

echo "Environment setup complete. Use 'conda activate $ENV_NAME' to activate it."
