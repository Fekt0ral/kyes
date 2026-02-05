import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base, RefreshToken

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register_and_login(client, email, password, name):
    client.post("/auth/register", json={
        "email": email,
        "password": password,
        "name": name
    })
    login_res = client.post("/auth/login", data={
        "username": email,
        "password": password
    })
    return login_res


def test_refresh_token_happy_path(client):
    login_res = register_and_login(client, "rt1@test.com", "StrongPass1!", "RT1")
    assert login_res.status_code == 200
    data = login_res.json()
    assert "refresh_token" in data

    refresh_res = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refresh_res.status_code == 200
    refreshed = refresh_res.json()
    assert "access_token" in refreshed
    assert "refresh_token" in refreshed
    assert refreshed["refresh_token"] != data["refresh_token"]


def test_refresh_token_rotation_reuse_denied(client):
    login_res = register_and_login(client, "rt2@test.com", "StrongPass1!", "RT2")
    data = login_res.json()

    refresh_res = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refresh_res.status_code == 200

    reuse_res = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert reuse_res.status_code == 401


def test_logout_revokes_refresh_token(client):
    login_res = register_and_login(client, "rt3@test.com", "StrongPass1!", "RT3")
    refresh_token = login_res.json()["refresh_token"]

    logout_res = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 200

    refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 401


def test_refresh_token_expired(client, session):
    login_res = register_and_login(client, "rt4@test.com", "StrongPass1!", "RT4")
    refresh_token = login_res.json()["refresh_token"]

    token_hash = __import__("hashlib").sha256(refresh_token.encode("utf-8")).hexdigest()
    db_token = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one()
    db_token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.commit()

    refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 401


def test_refresh_token_invalidated_by_password_change(client):
    email = "rt5@test.com"
    old_password = "StrongPass1!"
    new_password = "NewStrong1!"
    login_res = register_and_login(client, email, old_password, "RT5")
    refresh_token = login_res.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    change_res = client.patch(
        "/auth/me",
        json={"current_password": old_password, "password": new_password},
        headers=headers
    )
    assert change_res.status_code == 200

    refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 401
