import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

# Импортируем наше приложение и части, которые будем подменять
from app.main import app
from app.database import get_db
from app.models import Base
from app import schemas, security

# 1. Создаем временную БД в памяти (SQLite)
# "sqlite:///:memory:" означает, что файл не создается на диске
# connect_args={"check_same_thread": False} нужно для SQLite, чтобы работать в тестах
# StaticPool позволяет сохранять данные в памяти между запросами в рамках одного теста
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}, 
    poolclass=StaticPool
)

# 2. Создаем фабрику сессий для тестов
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Фикстура (fixture) — это функция, которая готовит окружение перед тестом
# Она создает таблицы, дает нам тестовый клиент и после теста всё удаляет
@pytest.fixture(name="client")
def client_fixture():
    # Создаем таблицы в тестовой БД
    Base.metadata.create_all(bind=engine)
    
    # Функция-заглушка, которая подменяет get_db
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    # Говорим FastAPI: "когда кто-то просит get_db, используй override_get_db"
    app.dependency_overrides[get_db] = override_get_db
    
    # Создаем клиента для запросов
    client = TestClient(app)
    
    yield client # Возвращаем клиента тесту
    
    # После теста: очищаем настройки и удаляем таблицы
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    
def test_user_validation_edges():
    # 1. Проверка валидного пользователя (Happy Path)
    valid_user = schemas.UserCreate(
        email="test@example.com",
        password="Password123!", # Есть буквы, цифры, спецсимвол, заглавная
        name="Valid Name"
    )
    assert valid_user.email == "test@example.com"

    # 2. ТЕСТ С ПОДВОХОМ: Пароль без спецсимвола
    # Ожидаем ошибку ValidationError
    with pytest.raises(ValidationError) as excinfo:
        schemas.UserCreate(
            email="test@example.com",
            password="Password123", # Забыли "!"
            name="Test"
        )
    # Проверяем, что ошибка именно там, где ждем
    assert "Password must be at least 8" in str(excinfo.value)

    # 3. ТЕСТ С ПОДВОХОМ: Пароль слишком короткий
    with pytest.raises(ValidationError):
        schemas.UserCreate(
            email="test@example.com",
            password="Aa1!", # Всего 4 символа
            name="Test"
        )

    # 4. ТЕСТ С ПОДВОХОМ: Имя только из цифр
    with pytest.raises(ValidationError) as excinfo:
        schemas.UserCreate(
            email="test@example.com",
            password="Password123!",
            name="123456" # Твой валидатор должен это запретить (contain letters...)
        )
    assert "Name must be between" in str(excinfo.value)

    # 5. ТЕСТ С ПОДВОХОМ: Имя со спецсимволами (кроме дефиса)
    with pytest.raises(ValidationError):
        schemas.UserCreate(
            email="test@example.com",
            password="Password123!",
            name="User_Name@" # @ запрещен
        )
    
    # 6. ТЕСТ: Имя с дефисом (должно работать)
    user_hyphen = schemas.UserCreate(
        email="test@example.com",
        password="Password123!",
        name="Anna-Maria"
    )
    assert user_hyphen.name == "Anna-Maria"
    
def test_register_user_success(client):
    # Данные для отправки
    payload = {
        "email": "newuser@example.com",
        "password": "StrongPassword1!",
        "name": "New User"
    }
    # Делаем POST запрос на /register (префикс тега users, но путь может быть /register)
    # В твоем файле users.py роутер не имеет префикса, но подключен в main.
    # Допустим, путь просто /register
    response = client.post("/auth/register", json=payload)
    
    # Проверяем статус 200 OK
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем, что вернулся email и id, но НЕ пароль
    assert data["email"] == payload["email"]
    assert "id" in data
    assert "password" not in data # Важно! Не светим пароль

def test_register_duplicate_email(client):
    payload = {
        "email": "duplicate@example.com",
        "password": "StrongPassword1!",
        "name": "User One"
    }
    # Создаем первого пользователя
    client.post("/auth/register", json=payload)
    
    # Пытаемся создать второго с ТЕМ ЖЕ email
    response = client.post("/auth/register", json=payload)
    
    # Ожидаем 400 Bad Request
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_register_duplicate_nickname(client):
    # Первый пользователь
    client.post("/auth/register", json={
        "email": "user1@example.com",
        "password": "StrongPassword1!",
        "name": "SuperUser"
    })
    
    # Второй пользователь: другой email, но ТОТ ЖЕ никнейм
    response = client.post("/auth/register", json={
        "email": "user2@example.com",
        "password": "StrongPassword1!",
        "name": "SuperUser" # Дубль
    })
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Nickname already taken"

def test_login_success(client):
    # 1. Сначала регистрируем
    email = "login@example.com"
    password = "MySuperPassword1!"
    client.post("/auth/register", json={
        "email": email,
        "password": password,
        "name": "Login User"
    })
    
    # 2. Пытаемся залогиниться
    # Обрати внимание: OAuth2PasswordRequestForm требует отправки данных как form-data,
    # поэтому используем data=..., а не json=...
    # И поле называется username, даже если мы передаем email (специфика OAuth2)
    login_data = {
        "username": "Login User", # У тебя логин по name (get_user_by_nickname)
        "password": password
    }
    
    response = client.post("/auth/login", data=login_data)
    
    assert response.status_code == 200
    token_data = response.json()
    
    # Проверяем структуру токена
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

def test_login_wrong_password(client):
    # Регистрируем
    client.post("/auth/register", json={
        "email": "wrong@example.com",
        "password": "CorrectPassword1!",
        "name": "WrongPassUser"
    })
    
    # Ломимся с неправильным паролем
    response = client.post("/auth/login", data={
        "username": "WrongPassUser",
        "password": "WrongPassword1!" 
    })
    
    assert response.status_code == 401
    assert "Incorrect username or password" in response.json()["detail"]
    
def test_password_hashing():
    password = "SecretPassword1!"
    
    # 1. Получаем хеш
    hashed = security.get_password_hash(password)
    
    # 2. Проверяем, что хеш НЕ равен паролю (мы не храним открытый текст)
    assert hashed != password
    
    # 3. Проверяем, что verify возвращает True для правильного пароля
    assert security.verify_password(password, hashed) is True
    
    # 4. Проверяем, что verify возвращает False для неправильного
    assert security.verify_password("WrongPassword", hashed) is False