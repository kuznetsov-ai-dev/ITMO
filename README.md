# Задание 3. ORM и подключение базы данных

## Описание

В рамках задания объектная модель ML-сервиса из первого задания была связана с реальной реляционной базой данных PostgreSQL через ORM SQLAlchemy.

Реализованы:

- ORM-модели таблиц
- связи между сущностями через Foreign Key
- работа с пользователями
- работа с балансом и историей транзакций
- история ML-запросов / предсказаний
- автоматическая инициализация БД демо-данными
- тестирование основных бизнес-сценариев

## Отображение объектной модели в БД

Отображение сущностей:

- `User` -> `users`
- `UserBalance` -> `user_balances`
- `MoneyMove` -> `balance_transactions`
- `Model` / `SimpleModel` -> `ml_models`
- `Task` / `TaskResult` -> `prediction_requests`

## Основные таблицы

Таблицы БД:

- `users`
- `user_balances`
- `balance_transactions`
- `ml_models`
- `prediction_requests`


### Пользователи

- создание пользователя
- загрузка пользователя из БД
- связь пользователя с балансом
- связь пользователя с историей транзакций
- роль пользователя: `user` / `admin`

### Баланс и транзакции

- пополнение баланса
- списание средств
- проверка достаточности средств перед списанием
- запись каждой операции в историю транзакций

### ML-запросы

- запуск предикта по выбранной модели
- запись истории запросов пользователя
- сортировка истории по дате
- сохранение стоимости операции
- связь запроса с конкретной ML-моделью

### Инициализация БД

При старте приложения автоматически создаются:

- демо-пользователь
- демо-администратор
- стартовые балансы
- базовые ML-модели

Инициализация сделана идемпотентной: повторный запуск не создаёт дубликаты.


## Структура проекта

~~~
ITMO/
├── app/
│   ├── src/
│   │   ├── api.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── domain_logic.py
│   │   ├── init_data.py
│   │   ├── models.py
│   │   ├── security.py
│   │   └── services.py
│   ├── tests/
│   │   └── test_task3_services.py
│   ├── .env
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── task_1/
├── web-proxy/
├── docker-compose.yml
└── README.md
~~~


## Команды запуска и проверки 

~~~
docker compose up --build

docker compose exec app python -m pytest -q tests
~~~


**Проверка health:**
~~~
curl http://localhost/health
~~~

**Cписок моделей:**
~~~
curl http://localhost/models
~~~

**Создание пользователя:**
~~~
curl -X POST http://localhost/users \
  -H "Content-Type: application/json" \
  -d '{
    "email": "new_user@mail.com",
    "password": "123456",
    "role": "user",
    "start_balance": "100.00"
  }'
~~~

**Пополнение баланса:**
~~~
curl -X POST http://localhost/users/1/balance/deposit \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "50.00",
    "description": "manual top up"
  }'
~~~

**Запуск предикта:**
~~~
curl -X POST http://localhost/predictions/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "model_id": 1,
    "rows": [
      {"value": 5},
      {"value": 12},
      {"name": "bad row"}
    ]
  }'

~~~
**История транзакций:**
~~~
curl http://localhost/users/1/transactions
~~~

**История предиктов:**
~~~
curl http://localhost/users/1/predictions
~~~