#!/usr/bin/env python3
"""
Script to test JWT functionality to verify the correct library is installed and working
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path so we can import the core.config module
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

# Load the environment variables
load_dotenv(parent_dir / ".env")

def test_jwt_encode_decode():
    """Test JWT encode and decode functionality"""
    print("Testing JWT functionality...")
    
    try:
        # Try importing jose.jwt
        from jose import jwt
        print("✓ Successfully imported jose.jwt")
        
        # Get JWT settings from environment
        from core.config import get_settings
        settings = get_settings()
        
        JWT_SECRET_KEY = settings.JWT_SECRET_KEY
        JWT_ALGORITHM = settings.JWT_ALGORITHM
        
        # Test encoding a token
        test_data = {"sub": "test", "role": "user"}
        print(f"Attempting to encode data: {test_data}")
        token = jwt.encode(test_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        print(f"✓ Successfully encoded token: {token[:20]}...")
        
        # Test decoding the token
        print("Attempting to decode the token...")
        decoded = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        print(f"✓ Successfully decoded token: {decoded}")
        
        print("\nJWT functionality test PASSED!")
        return True
    
    except ImportError as e:
        print(f"✗ Failed to import JWT module: {str(e)}")
        print("Make sure 'python-jose' is installed with: pip install python-jose[cryptography]")
        return False
    except Exception as e:
        print(f"✗ JWT test failed with error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_jwt_encode_decode()
    sys.exit(0 if success else 1)
