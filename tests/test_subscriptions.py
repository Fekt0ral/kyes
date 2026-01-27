import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from datetime import date

from app.main import app
from app.database import get_db
from app.models import Base
from app.currency import get_rates
from app import schemas, models, security

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
    
    # Заглушка для курсов валют, чтобы не ходить в интернет
    def override_get_rates():
        return {"USD": 0.01, "EUR": 0.009, "RUB": 1.0}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rates] = override_get_rates
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client, session):
    user_data = {"email": "tester@test.com", "name": "Tester", "password": "Password123!"}
    hashed = security.get_password_hash(user_data["password"])
    db_user = models.User(email=user_data["email"], name=user_data["name"], hashed_password=hashed)
    session.add(db_user)
    session.commit()
    
    token = security.create_access_token(data={"sub": user_data["email"]})
    return {"Authorization": f"Bearer {token}"}

def test_subscription_schema_validation():
    with pytest.raises(Exception):
        schemas.SubscriptionCreate(
            service_name="Netflix",
            price=-10.0, # Отрицательная цена
            currency="USD",
            next_payment=date.today()
        )

    with pytest.raises(Exception):
        schemas.SubscriptionCreate(
            service_name="Netflix",
            price=10.0,
            currency="YEN", # Недопустимая валюта
            next_payment=date.today()
        )

def test_currency_conversion():
    from app.currency import convert_to_rub
    rates = {"USD": 0.01} # 1 / 0.01 = 100
    
    # Проверяем, что 10 долларов конвертируются в 1000 рублей
    result = convert_to_rub(10.0, "USD", rates)
    assert result == 1000.0
    
def test_create_subscription_api(client, auth_headers):
    payload = {
        "service_name": "Spotify",
        "price": 5.0,
        "currency": "USD",
        "next_payment": str(date.today()),
        "category": "Music"
    }
    response = client.post("/subs/", json=payload, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["service_name"] == "Spotify"

def test_get_subs_and_report(client, auth_headers):
    # Создаем две подписки через API
    client.post("/subs/", json={"service_name": "S1", "price": 100, "currency": "RUB", "next_payment": "2025-01-01", "category": "Work"}, headers=auth_headers)
    client.post("/subs/", json={"service_name": "S2", "price": 10, "currency": "USD", "next_payment": "2025-01-01", "category": "Work"}, headers=auth_headers)
    
    # 1. Проверяем список
    resp_list = client.get("/subs/", headers=auth_headers)
    assert len(resp_list.json()) == 2
    # Проверяем, что цена в рублях рассчиталась (100 + 10*100 = 1100)
    assert resp_list.json()[1]["price_rub"] == 1000.0

    # 2. Проверяем общий отчет
    resp_report = client.get("/subs/report", headers=auth_headers)
    assert resp_report.json()["total_monthly"] == 1100.0

def test_delete_and_security_trick(client, session, auth_headers):
    # 1. Создаем подписку первого (основного) пользователя
    sub_payload = {"service_name": "DeleteMe", "price": 1, "currency": "RUB", "next_payment": "2025-01-01"}
    sub_res = client.post("/subs/", json=sub_payload, headers=auth_headers).json()
    sub_id = sub_res["id"]

    # 2. РЕГИСТРИРУЕМ второго пользователя в базе (чтобы он существовал)
    other_user_data = {"email": "hacker@test.com", "password": "Password123!", "name": "Hacker"}
    # Хешируем пароль и сохраняем в БД
    from app.security import get_password_hash
    db_hacker = models.User(
        email=other_user_data["email"], 
        name=other_user_data["name"], 
        hashed_password=get_password_hash(other_user_data["password"])
    )
    session.add(db_hacker)
    session.commit()

    # 3. Создаем токен для существующего второго пользователя
    other_token = security.create_access_token(data={"sub": other_user_data["email"]})
    other_headers = {"Authorization": f"Bearer {other_token}"}
    
    # 4. Теперь он авторизован (пройдет 401), но подписка не его
    # crud.delete_subscription вернет None, и роутер выдаст 404
    fail_resp = client.delete(f"/subs/{sub_id}", headers=other_headers)
    
    # Теперь этот ассерт сработает правильно
    assert fail_resp.status_code == 404 
    assert fail_resp.json()["detail"] == "Subscription not found or access denied"
    
    # Удаляем подписку законным владельцем
    success_resp = client.delete(f"/subs/{sub_id}", headers=auth_headers)

    # Теперь мы ждем 204 (No Content), а не 200
    assert success_resp.status_code == 204 

    # Важно: при 204 тело ответа пустое, поэтому не пытайся делать .json()
    assert success_resp.text == ""