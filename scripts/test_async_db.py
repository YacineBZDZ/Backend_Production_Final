#!/usr/bin/env python3
"""
Script to test async database connections
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import text

# Add parent directory to path for imports
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from database.session import get_async_session, get_async_db_context, close_db_connections


async def test_async_session():
    """Test the async session functionality using async for"""
    print("\nTesting async database connection with async for...")
    try:
        session = None
        async for session_obj in get_async_session():
            session = session_obj
            break
        
        if not session:
            print("❌ Failed to get session")
            return False
            
        # Try a simple query - use text() to properly declare SQL
        result = await session.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        if row and row[0] == 1:
            print("✅ Async database connection successful with async for!")
        else:
            print("❌ Async query returned unexpected result")
            return False
            
        await session.close()
        return True
    except Exception as e:
        print(f"❌ Async database connection failed: {str(e)}")
        return False


async def test_async_context():
    """Test the async session functionality using async with"""
    print("\nTesting async database connection with async with...")
    try:
        async with get_async_db_context() as session:
            # Try a simple query - use text() to properly declare SQL
            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            if row and row[0] == 1:
                print("✅ Async database connection successful with async with!")
            else:
                print("❌ Async query returned unexpected result")
                return False
        return True
    except Exception as e:
        print(f"❌ Async database connection failed: {str(e)}")
        return False


async def run_tests():
    """Run all tests"""
    try:
        test1 = await test_async_session()
        test2 = await test_async_context()
        return test1 and test2
    finally:
        # Clean up connections at the end
        await close_db_connections()


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
