import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from datetime import date, timedelta

from app.main import app
from app.database import get_db
from app.models import Base
from app.currency import get_rates
from app import schemas

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
    
    def override_get_rates():
        return {"USD": 0.01, "EUR": 0.009, "RUB": 1.0}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rates] = override_get_rates
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client):
    email = "test@example.com"
    password = "StrongPassword1!"
    client.post("/auth/register", json={
        "email": email,
        "password": password,
        "name": "Tester"
    })
    login_res = client.post("/auth/login", data={
        "username": email, 
        "password": password
    })
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_subscription_schema_validation():
    valid_data = {
        "service_name": "Netflix",
        "price": 9.99,
        "currency": "USD",
        "next_payment": date.today() + timedelta(days=1)
    }
    assert schemas.SubscriptionCreate(**valid_data)

def test_currency_conversion(client, auth_headers):
    payload = {
        "service_name": "Netflix",
        "price": 10.0,
        "currency": "USD",
        "next_payment": str(date.today())
    }
    res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["price_rub"] == 1000.0

def test_create_subscription_api(client, auth_headers):
    payload = {
        "service_name": "Spotify",
        "price": 300.0,
        "currency": "RUB",
        "next_payment": str(date.today()),
        "category": "Music"
    }
    response = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["service_name"] == "Spotify"
    assert "id" in data

def test_get_subs_and_report(client, auth_headers):
    client.post("/subscriptions/", json={"service_name": "S1", "price": 100, "currency": "RUB", "next_payment": str(date.today()), "category": "Work"}, headers=auth_headers)
    client.post("/subscriptions/", json={"service_name": "S2", "price": 10, "currency": "USD", "next_payment": str(date.today()), "category": "Work"}, headers=auth_headers)

    resp_list = client.get("/subscriptions/", headers=auth_headers)
    assert len(resp_list.json()) == 2
    assert resp_list.json()[1]["price_rub"] == 1000.0

    resp_report = client.get("/subscriptions/reports/summary", headers=auth_headers)
    assert resp_report.json()["total_monthly"] == 1100.0

def test_delete_and_security_trick(client, session, auth_headers):
    payload = {"service_name": "Secret", "price": 10, "currency": "RUB", "next_payment": str(date.today())}
    sub_id = client.post("/subscriptions/", json=payload, headers=auth_headers).json()["id"]
    
    del_res = client.delete(f"/subscriptions/{sub_id}", headers=auth_headers)
    assert del_res.status_code == 204

def test_update_subscription_success(client, auth_headers):
    payload = {"service_name": "Netflix", "price": 10.0, "currency": "USD", "next_payment": "2026-02-01", "category": "Cinema"}
    sub_id = client.post("/subscriptions/", json=payload, headers=auth_headers).json()["id"]
    
    update_payload = {"price": 15.0}
    patch_res = client.patch(f"/subscriptions/update/{sub_id}", json=update_payload, headers=auth_headers)
    
    assert patch_res.status_code == 200
    assert patch_res.json()["price"] == 15.0

def test_update_subscription_unauthorized(client, session, auth_headers):
    payload = {"service_name": "MySub", "price": 100, "currency": "RUB", "next_payment": "2026-02-01"}
    sub_id = client.post("/subscriptions/", json=payload, headers=auth_headers).json()["id"]

    hacker_email = "hacker@test.com"
    client.post("/auth/register", json={"email": hacker_email, "password": "StrongPassword1!", "name": "Hacker"})
    login_res = client.post("/auth/login", data={"username": hacker_email, "password": "StrongPassword1!"})
    h_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    patch_res = client.patch(f"/subscriptions/update/{sub_id}", json={"price": 1.0}, headers=h_headers)
    assert patch_res.status_code == 404

def test_create_subscription_past_date(client, auth_headers):
    past_date = date.today() - timedelta(days=1)
    payload = {"service_name": "Old", "price": 100.0, "currency": "RUB", "next_payment": str(past_date)}
    response = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert response.status_code == 422

def test_update_subscription_past_date(client, auth_headers):
    payload = {"service_name": "Future", "price": 100.0, "currency": "RUB", "next_payment": str(date.today() + timedelta(days=5))}
    sub_id = client.post("/subscriptions/", json=payload, headers=auth_headers).json()["id"]
    
    past_date = str(date.today() - timedelta(days=1))
    response = client.patch(f"/subscriptions/update/{sub_id}", json={"next_payment": past_date}, headers=auth_headers)
    assert response.status_code == 422