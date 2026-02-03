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
    assert res.status_code == 201
    assert res.json()["display_price"] == 1000.0
    assert res.json()["display_currency"] == "RUB"

def test_create_subscription_api(client, auth_headers):
    payload = {
        "service_name": "Spotify",
        "price": 300.0,
        "currency": "RUB",
        "next_payment": str(date.today()),
        "category": "Music"
    }
    response = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["service_name"] == "Spotify"
    assert "id" in data

def test_get_subs_and_report(client, auth_headers):
    client.post("/subscriptions/", json={"service_name": "S1", "price": 100, "currency": "RUB", "next_payment": str(date.today()), "category": "Work"}, headers=auth_headers)
    client.post("/subscriptions/", json={"service_name": "S2", "price": 10, "currency": "USD", "next_payment": str(date.today()), "category": "Work"}, headers=auth_headers)

    resp_list = client.get("/subscriptions/", headers=auth_headers)
    assert len(resp_list.json()) == 2
    assert resp_list.json()[0]["display_price"] == 1000.0
    assert resp_list.json()[0]["display_currency"] == "RUB"

    resp_report = client.get("/subscriptions/reports/summary", headers=auth_headers)
    assert resp_report.json()["total_monthly"] == 1100.0
    assert resp_report.json()["currency"] == "RUB"

def test_delete_and_security_trick(client, session, auth_headers):
    payload = {"service_name": "Secret", "price": 10, "currency": "RUB", "next_payment": str(date.today())}
    sub_id = client.post("/subscriptions/", json=payload, headers=auth_headers).json()["id"]
    
    del_res = client.delete(f"/subscriptions/{sub_id}", headers=auth_headers)
    assert del_res.status_code == 204

def test_update_subscription_success(client, auth_headers):
    payload = {"service_name": "NetflixUpdate", "price": 10.0, "currency": "USD", "next_payment": str(date.today()), "category": "Cinema"}
    create_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert create_res.status_code == 201, f"Failed to create subscription: {create_res.json()}"
    sub_id = create_res.json()["id"]
    
    update_payload = {"price": 15.0}
    patch_res = client.patch(f"/subscriptions/update/{sub_id}", json=update_payload, headers=auth_headers)
    
    assert patch_res.status_code == 200
    assert patch_res.json()["price"] == 15.0

def test_update_subscription_unauthorized(client, session, auth_headers):
    payload = {"service_name": "MySubUnauth", "price": 100, "currency": "RUB", "next_payment": str(date.today())}
    create_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert create_res.status_code == 201, f"Failed to create subscription: {create_res.json()}"
    sub_id = create_res.json()["id"]

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

# ========== Тесты для функционала дубликатов ==========

def test_duplicate_subscription_warning(client, auth_headers):
    """Тест: создание дубликата без force возвращает 409 с предупреждением"""
    payload = {
        "service_name": "DuplicateTest",
        "price": 100.0,
        "currency": "RUB",
        "next_payment": str(date.today()),
        "category": "Test"
    }
    
    # Первое создание - успешно
    first_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert first_res.status_code == 201
    assert first_res.json()["service_name"] == "DuplicateTest"
    
    # Второе создание без force - 409 Conflict
    second_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert second_res.status_code == 409
    
    detail = second_res.json()["detail"]
    assert detail["warning"] == "duplicate_subscription"
    assert "DuplicateTest" in detail["message"]
    assert "force=true" in detail["message"]
    assert len(detail["existing_subscriptions"]) == 1
    assert detail["existing_subscriptions"][0]["service_name"] == "DuplicateTest"

def test_duplicate_subscription_with_force(client, auth_headers):
    """Тест: создание дубликата с force=true создаёт вторую подписку"""
    payload = {
        "service_name": "ForceTest",
        "price": 200.0,
        "currency": "RUB",
        "next_payment": str(date.today()),
        "category": "Test"
    }
    
    # Первое создание
    first_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert first_res.status_code == 201
    first_id = first_res.json()["id"]
    
    # Второе создание с force=true
    second_res = client.post("/subscriptions/?force=true", json=payload, headers=auth_headers)
    assert second_res.status_code == 201
    second_id = second_res.json()["id"]
    
    # Проверяем, что созданы две разные подписки
    assert first_id != second_id
    
    # Проверяем, что обе подписки существуют
    all_subs = client.get("/subscriptions/", headers=auth_headers).json()
    force_test_subs = [s for s in all_subs if s["service_name"] == "ForceTest"]
    assert len(force_test_subs) == 2

def test_duplicate_check_shows_existing_details(client, auth_headers):
    """Тест: предупреждение о дубликате содержит детали существующих подписок"""
    payload = {
        "service_name": "DetailTest",
        "price": 500.0,
        "currency": "USD",
        "next_payment": "2026-03-15",
        "category": "Premium",
        "link": "https://detailtest.com"
    }
    
    # Создаём первую подписку
    first_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert first_res.status_code == 201
    
    # Пытаемся создать дубликат
    dup_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert dup_res.status_code == 409
    
    existing = dup_res.json()["detail"]["existing_subscriptions"][0]
    assert existing["price"] == 500.0
    assert existing["currency"] == "USD"
    assert existing["next_payment"] == "2026-03-15"
    assert existing["category"] == "Premium"
    assert existing["link"] == "https://detailtest.com"
    assert "display_price" in existing  # Проверяем конвертацию валюты
    assert "display_currency" in existing

def test_multiple_duplicates_listed(client, auth_headers):
    """Тест: если несколько дубликатов, все показываются в предупреждении"""
    payload = {
        "service_name": "MultiDup",
        "price": 100.0,
        "currency": "RUB",
        "next_payment": str(date.today())
    }
    
    # Создаём первую подписку
    client.post("/subscriptions/", json=payload, headers=auth_headers)
    
    # Создаём вторую с force=true
    client.post("/subscriptions/?force=true", json=payload, headers=auth_headers)
    
    # Пытаемся создать третью без force
    third_res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert third_res.status_code == 409
    
    # Проверяем, что показаны обе существующие подписки
    existing = third_res.json()["detail"]["existing_subscriptions"]
    assert len(existing) == 2


def test_display_currency_respects_user_preference(client, auth_headers):
    pref_res = client.patch("/auth/me/preferences", json={"preferred_currency": "USD"}, headers=auth_headers)
    assert pref_res.status_code == 200

    payload = {
        "service_name": "Local",
        "price": 1000.0,
        "currency": "RUB",
        "next_payment": str(date.today())
    }
    res = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["display_price"] == 10.0
    assert res.json()["display_currency"] == "USD"

    list_res = client.get("/subscriptions/", headers=auth_headers)
    assert list_res.json()[0]["display_currency"] == "USD"


def test_reports_use_preferred_currency(client, auth_headers):
    client.patch("/auth/me/preferences", json={"preferred_currency": "EUR"}, headers=auth_headers)

    client.post("/subscriptions/", json={"service_name": "R1", "price": 1000, "currency": "RUB", "next_payment": str(date.today()), "category": "AA"}, headers=auth_headers)
    client.post("/subscriptions/", json={"service_name": "U1", "price": 10, "currency": "USD", "next_payment": str(date.today()), "category": "AA"}, headers=auth_headers)

    report = client.get("/subscriptions/reports/summary", headers=auth_headers).json()
    assert report["currency"] == "EUR"
    assert report["total_monthly"] == 18.0

    cat_report = client.get("/subscriptions/reports/AA", headers=auth_headers).json()
    assert cat_report["currency"] == "EUR"
    assert cat_report["total_monthly"] == 18.0

    avg = client.get("/subscriptions/average/AA", headers=auth_headers).json()
    assert avg["currency"] == "EUR"
    assert avg["average_price"] == 9.0

def test_different_service_names_no_conflict(client, auth_headers):
    """Тест: разные названия сервисов не конфликтуют"""
    payload1 = {
        "service_name": "Service1",
        "price": 100.0,
        "currency": "RUB",
        "next_payment": str(date.today())
    }
    payload2 = {
        "service_name": "Service2",
        "price": 100.0,
        "currency": "RUB",
        "next_payment": str(date.today())
    }
    
    res1 = client.post("/subscriptions/", json=payload1, headers=auth_headers)
    assert res1.status_code == 201
    
    res2 = client.post("/subscriptions/", json=payload2, headers=auth_headers)
    assert res2.status_code == 201

def test_duplicate_check_user_isolation(client, auth_headers):
    """Тест: проверка дубликатов изолирована между пользователями"""
    payload = {
        "service_name": "IsolationTest",
        "price": 100.0,
        "currency": "RUB",
        "next_payment": str(date.today())
    }
    
    # Первый пользователь создаёт подписку
    res1 = client.post("/subscriptions/", json=payload, headers=auth_headers)
    assert res1.status_code == 201
    
    # Создаём второго пользователя
    user2_email = "user2@test.com"
    client.post("/auth/register", json={
        "email": user2_email,
        "password": "StrongPassword2!",
        "name": "User2"
    })
    login_res = client.post("/auth/login", data={
        "username": user2_email,
        "password": "StrongPassword2!"
    })
    user2_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    
    # Второй пользователь может создать подписку с тем же названием без конфликта
    res2 = client.post("/subscriptions/", json=payload, headers=user2_headers)
    assert res2.status_code == 201
    
    # Проверяем, что у каждого пользователя своя подписка
    user1_subs = client.get("/subscriptions/", headers=auth_headers).json()
    user2_subs = client.get("/subscriptions/", headers=user2_headers).json()
    
    user1_isolation = [s for s in user1_subs if s["service_name"] == "IsolationTest"]
    user2_isolation = [s for s in user2_subs if s["service_name"] == "IsolationTest"]
    
    assert len(user1_isolation) == 1
    assert len(user2_isolation) == 1
    assert user1_isolation[0]["id"] != user2_isolation[0]["id"]
