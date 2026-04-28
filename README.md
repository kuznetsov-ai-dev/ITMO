# ITMO ML Service — финальный проект

Финальный проект блока: web- и REST-сервис для выполнения ML-запросов с авторизацией, балансом пользователя, историей операций и асинхронной обработкой задач через RabbitMQ.

## Что умеет проект

- Регистрация и авторизация пользователей.
- Web-интерфейс на FastAPI + Jinja2.
- REST API для основных пользовательских сценариев.
- Личный кабинет пользователя.
- Пополнение баланса.
- Список доступных ML-моделей.
- Создание ML-запроса.
- Асинхронная обработка ML-задач через RabbitMQ.
- Worker-процессы для обработки задач.
- Сохранение истории ML-запросов.
- Сохранение истории транзакций.
- Админ-панель для просмотра пользователей и транзакций.
- Интеграционные тесты основных сценариев.

## Технологии

- Python 3.12
- FastAPI
- Jinja2
- SQLAlchemy
- PostgreSQL
- RabbitMQ
- Pika
- Docker Compose
- Nginx
- Pytest

## Архитектура

Проект состоит из нескольких сервисов:

- `app` — FastAPI-приложение, REST API и web-интерфейс.
- `worker-1`, `worker-2` — worker-процессы, которые читают задачи из RabbitMQ и выполняют ML-обработку.
- `database` — PostgreSQL для хранения пользователей, балансов, транзакций, моделей и ML-запросов.
- `rabbitmq` — очередь задач для асинхронной обработки.
- `web-proxy` — nginx reverse proxy.

Общая логика работы:

1. Пользователь регистрируется или входит в систему.
2. Пользователь пополняет баланс.
3. Пользователь выбирает ML-модель и отправляет данные.
4. Приложение создаёт задачу и кладёт сообщение в RabbitMQ.
5. Worker получает задачу из очереди.
6. Worker выполняет обработку данных.
7. Результат сохраняется в PostgreSQL.
8. Пользователь смотрит статус и результат в истории.

## Структура проекта

```text
ITMO
├── app
│   ├── src
│   │   ├── routers
│   │   │   ├── admin.py
│   │   │   ├── auth.py
│   │   │   ├── balance.py
│   │   │   ├── history.py
│   │   │   ├── predict.py
│   │   │   ├── system.py
│   │   │   ├── users.py
│   │   │   └── web.py
│   │   ├── api.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── dependencies.py
│   │   ├── domain_logic.py
│   │   ├── init_data.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   ├── web_auth.py
│   │   ├── web_utils.py
│   │   └── worker.py
│   ├── static
│   │   └── style.css
│   ├── templates
│   ├── tests
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── web-proxy
│   └── nginx.conf
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Быстрый запуск

### 1. Подготовить переменные окружения

```bash
cp app/.env.example app/.env
```

### 2. Остановить старые контейнеры и удалить старые volume

Команда нужна для полностью чистого запуска:

```bash
docker compose down -v
```

### 3. Собрать и запустить проект

```bash
docker compose up --build
```

После запуска приложение будет доступно через nginx:

```text
http://localhost
```

Документация FastAPI:

```text
http://localhost/docs
```

RabbitMQ Management UI:

```text
http://localhost:15672
```

Данные для RabbitMQ:

```text
login: itmo_rabbit
password: itmo_rabbit_pass
```

## Проверка запуска

В отдельном терминале:

```bash
docker compose ps
```

Проверка health endpoint:

```bash
curl http://localhost/health
```

Ожидаемый успешный ответ:

```json
{
  "status": "ok",
  "database": true,
  "rabbitmq": true
}
```

## Демо-аккаунты

При старте приложения автоматически создаются демо-пользователи и демо-модели.

Обычный пользователь:

```text
login: demo_user
password: user123
email: demo.user@mail.com
```

Администратор:

```text
login: demo_admin
password: admin123
email: demo.admin@mail.com
```

## Демо-модели

```text
simple-quality-model — цена 25.00
simple-fast-model    — цена 15.00
demo_model           — цена 10.00
```

## Web-интерфейс

Главная страница:

```text
http://localhost
```

Основные страницы:

```text
/login
/register
/cabinet
/cabinet/predict
/cabinet/history
/admin
```

Сценарий проверки через web:

1. Открыть `http://localhost`.
2. Зарегистрировать нового пользователя.
3. Войти в систему.
4. Открыть личный кабинет.
5. Пополнить баланс.
6. Открыть страницу ML-запроса.
7. Выбрать модель `demo_model`.
8. Отправить JSON с признаками.
9. Открыть историю.
10. Дождаться статуса `done`.
11. Проверить результат ML-запроса и списание средств.
12. Войти под администратором и открыть админ-панель.

Пример JSON для одной записи:

```json
{
  "x1": 5,
  "x2": 7.5,
  "x3": 2.5
}
```

Ожидаемый результат demo-модели — сумма признаков:

```text
15.0
```

## REST API

REST API использует HTTP Basic Auth.

### Регистрация

```bash
curl -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "login": "api_user",
    "email": "api.user@mail.com",
    "password": "123456"
  }'
```

### Авторизация

```bash
curl -X POST http://localhost/auth/login \
  -u api_user:123456
```

### Получить профиль

```bash
curl http://localhost/users/me \
  -u api_user:123456
```

### Пополнить баланс

```bash
curl -X POST http://localhost/balance/deposit \
  -u api_user:123456 \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.00",
    "description": "demo deposit"
  }'
```

### Получить баланс

```bash
curl http://localhost/balance \
  -u api_user:123456
```

### Получить список моделей

```bash
curl http://localhost/models \
  -u api_user:123456
```

### Создать ML-задачу

```bash
curl -X POST http://localhost/predict \
  -u api_user:123456 \
  -H "Content-Type: application/json" \
  -d '{
    "model": "demo_model",
    "features": {
      "x1": 5,
      "x2": 7.5,
      "x3": 2.5
    }
  }'
```

Ответ содержит `task_id`. По нему можно получить статус задачи.

### Получить статус и результат задачи

```bash
curl http://localhost/predict/<TASK_ID> \
  -u api_user:123456
```

### История ML-запросов

```bash
curl http://localhost/history/predictions \
  -u api_user:123456
```

### История транзакций

```bash
curl http://localhost/history/transactions \
  -u api_user:123456
```

## Тесты

Запуск тестов внутри контейнера приложения:

```bash
docker compose exec app python -m pytest -v tests
```

Краткий запуск:

```bash
docker compose exec app python -m pytest -q tests
```

Тесты проверяют ключевые сценарии:

- регистрация и авторизация;
- повторный вход пользователя;
- ошибка при неверном пароле;
- получение и пополнение баланса;
- создание ML-задачи;
- обработка задачи worker-ом;
- получение статуса `done`;
- сохранение истории ML-запросов;
- сохранение истории транзакций;
- проверка обработки некорректных данных.

## Команды для демонстрации

Полный чистый запуск:

```bash
docker compose down -v
docker compose up --build
```

Проверить сервисы:

```bash
docker compose ps
curl http://localhost/health
```

Запустить тесты:

```bash
docker compose exec app python -m pytest -v tests
```

Посмотреть логи worker-ов:

```bash
docker compose logs -f worker-1 worker-2
```
