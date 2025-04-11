#!/bin/bash

# Script to install the correct dependency versions for the TabibMeet backend

echo "Installing or updating dependencies..."

# Clean up any potentially conflicting packages
pip uninstall -y fastapi pydantic pydantic-settings PyJWT jwt

# Install fastapi and pydantic with compatible versions
pip install "fastapi>=0.100.0" "pydantic>=2.0.0" "pydantic-settings>=2.0.0"

# Install python-jose for JWT handling
pip install "python-jose[cryptography]>=3.3.0"

# Install passlib for password hashing
pip install "passlib[bcrypt]>=1.7.4"

# Now install all other dependencies
pip install -r requirements.txt

# Check for any dependency conflicts
echo "Checking for dependency conflicts..."
pip check

if [ $? -eq 0 ]; then
    echo "All dependencies installed successfully with no conflicts."
else
    echo "Warning: There may be dependency conflicts. Please review the output above."
    
    # Display installed versions of key packages
    echo "Installed package versions:"
    pip show fastapi pydantic pydantic-settings python-jose | grep -E "Name|Version"
fi
