#!/usr/bin/env python3
"""
Script to verify all required environment variables are present
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path so we can import the core.config module
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

try:
    from core.config import Settings
except ImportError:
    print("Error: Unable to import Settings class from core.config module.")
    sys.exit(1)

def load_env_files():
    """Load environment variables from .env files"""
    env_files = [
        parent_dir / ".env",
        parent_dir / ".env.local",
        parent_dir / ".env.development",
        parent_dir / ".env.production",
    ]
    
    for env_file in env_files:
        if env_file.exists():
            print(f"Loading environment variables from {env_file}")
            load_dotenv(env_file)

def main():
    """Main function to verify environment variables"""
    load_env_files()
    
    print("Verifying environment variables...")
    
    try:
        # Create Settings instance to trigger validation
        settings = Settings()
        print("Environment validation successful!")
        
        # Print all settings for verification
        print("\nCurrent configuration:")
        for key, value in settings.model_dump().items():
            # Hide sensitive values
            if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'token']):
                value = '*****'
            print(f"{key}: {value}")
        
    except Exception as e:
        print(f"Environment validation failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
