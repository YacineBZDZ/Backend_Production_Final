import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.session import get_db
from models.user import User, UserRole
from models.authentication import AuthHandler
from database.base import Base

from main import app  # Use absolute import

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="module")
def test_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

def test_refresh_token(test_db):
    # Create a test user
    user = User(
        email="test@example.com",
        password=AuthHandler.get_password_hash("TestPassword123!"),
        salt=AuthHandler.generate_salt(),
        first_name="Test",
        last_name="User",
        phone="+1234567890",
        role=UserRole.PATIENT,
        refresh_token=None,
        login_attempts=0,
        locked_until=None,
        last_login=None,
        last_ip=None,
        two_factor_secret=None,
        two_factor_enabled=False,
        reset_token=None,
        reset_token_expires=None
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Log in to get a refresh token
    response = client.post(
        "/services/login",
        data={"username": "test@example.com", "password": "TestPassword123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    tokens = response.json()
    refresh_token = tokens["refresh_token"]

    # Use the refresh token to get a new access token
    response = client.post(
        "/services/refresh-token",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["token_type"] == "bearer"
    assert new_tokens["expires_in"] == 3600
    assert new_tokens["user_id"] == user.id
    assert new_tokens["role"] == user.role.value

def test_register_login_refresh_token(test_db):
    # Register a new user
    response = client.post(
        "/services/register",
        json={
            "email": "newuser2@example.com",
            "password": "NewUserPassword1234!",
            "confirm_password": "NewUserPassword1234!",
            "first_name": "Nep",
            "last_name": "Usep",
            "phone": "+1234567892",
            "role": UserRole.PATIENT.value
        }
    )
    assert response.status_code == 201
    user_id = response.json()["user_id"]

    # Log in with the new user
    response = client.post(
        "/services/login",
        data={"username": "newuser2@example.com", "password": "NewUserPassword1234!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    tokens = response.json()
    refresh_token = tokens["refresh_token"]

    # Use the refresh token to get a new access token
    response = client.post(
        "/services/refresh-token",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["token_type"] == "bearer"
    assert new_tokens["expires_in"] == 3600
    assert new_tokens["user_id"] == user_id
    assert new_tokens["role"] == UserRole.PATIENT.value