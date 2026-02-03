import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base, User

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


def register_and_login(client, email, password, name, preferred_currency="RUB"):
    client.post("/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "preferred_currency": preferred_currency
    })
    login_res = client.post("/auth/login", data={
        "username": email,
        "password": password
    })
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_update_me_requires_current_password(client):
    headers = register_and_login(client, "a@test.com", "StrongPass1!", "Alice")
    res = client.patch("/auth/me", json={"password": "NewStrong1!"}, headers=headers)
    assert res.status_code == 400
    assert res.json()["detail"] == "Current password is required to change password"


def test_update_me_wrong_current_password(client):
    headers = register_and_login(client, "b@test.com", "StrongPass1!", "Bob")
    res = client.patch(
        "/auth/me",
        json={"current_password": "WrongPass1!", "password": "NewStrong1!"},
        headers=headers
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect current password"


def test_update_me_change_password_invalidates_old_token(client):
    email = "c@test.com"
    old_password = "StrongPass1!"
    new_password = "NewStrong1!"
    headers = register_and_login(client, email, old_password, "Carol")

    res = client.patch(
        "/auth/me",
        json={"current_password": old_password, "password": new_password},
        headers=headers
    )
    assert res.status_code == 200

    res_old = client.get("/auth/me", headers=headers)
    assert res_old.status_code == 401
    assert res_old.json()["detail"] == "Token invalidated by password change"

    login_res = client.post("/auth/login", data={"username": email, "password": new_password})
    assert login_res.status_code == 200


def test_update_me_email_duplicate(client):
    headers1 = register_and_login(client, "d1@test.com", "StrongPass1!", "D1")
    register_and_login(client, "d2@test.com", "StrongPass1!", "D2")

    res = client.patch("/auth/me", json={"email": "d2@test.com"}, headers=headers1)
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already registered"


def test_update_me_no_changes(client):
    headers = register_and_login(client, "e@test.com", "StrongPass1!", "Eve")
    res = client.patch("/auth/me", json={}, headers=headers)
    assert res.status_code == 400
    assert res.json()["detail"] == "No changes to update"


def test_update_me_name_cooldown_and_reset(client, session):
    headers = register_and_login(client, "f@test.com", "StrongPass1!", "Frank")

    res1 = client.patch("/auth/me", json={"name": "Franklin"}, headers=headers)
    assert res1.status_code == 200

    res2 = client.patch("/auth/me", json={"name": "Frank2"}, headers=headers)
    assert res2.status_code == 429
    assert res2.json()["detail"] == "Name can be changed once per day"

    user = session.execute(select(User).where(User.email == "f@test.com")).scalar_one()
    user.last_name_change = datetime.now(timezone.utc) - timedelta(days=2)
    session.commit()

    res3 = client.patch("/auth/me", json={"name": "Frank3"}, headers=headers)
    assert res3.status_code == 200


def test_update_me_email_cooldown(client):
    headers = register_and_login(client, "g@test.com", "StrongPass1!", "Gina")

    res1 = client.patch("/auth/me", json={"email": "g2@test.com"}, headers=headers)
    assert res1.status_code == 200

    res2 = client.patch("/auth/me", json={"email": "g3@test.com"}, headers=headers)
    assert res2.status_code == 429
    assert res2.json()["detail"] == "Email can be changed once per day"

    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "g2@test.com"


def test_update_me_password_cooldown(client):
    email = "h@test.com"
    old_password = "StrongPass1!"
    new_password = "NewStrong1!"
    headers = register_and_login(client, email, old_password, "Hank")

    res1 = client.patch(
        "/auth/me",
        json={"current_password": old_password, "password": new_password},
        headers=headers
    )
    assert res1.status_code == 200

    login_res = client.post("/auth/login", data={"username": email, "password": new_password})
    new_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    res2 = client.patch(
        "/auth/me",
        json={"current_password": new_password, "password": "AnotherStrong1!"},
        headers=new_headers
    )
    assert res2.status_code == 429
    assert res2.json()["detail"] == "Password can be changed once per day"


def test_preferred_currency_update_and_me(client):
    headers = register_and_login(client, "i@test.com", "StrongPass1!", "Ivy")

    res = client.patch("/auth/me/preferences", json={"preferred_currency": "USD"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["preferred_currency"] == "USD"

    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["preferred_currency"] == "USD"
