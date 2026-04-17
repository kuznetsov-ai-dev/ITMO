# Задание 5. Взаимодействие с ML-сервисом через RabbitMQ

## Описание

В проекте реализовано асинхронное взаимодействие с ML-сервисом через RabbitMQ.

Система построена по схеме:

- один publisher — FastAPI приложение
- один broker — RabbitMQ
- одна очередь `ml_task_queue`
- два consumers — `worker-1` и `worker-2`

FastAPI принимает входящий запрос, формирует ML-задачу, сохраняет её в PostgreSQL и отправляет сообщение в очередь RabbitMQ.

Воркеры получают задачи из очереди, валидируют входные данные, выполняют mock ML-predict и сохраняют результат обработки в базе данных.

---

## Реализованные компоненты

### 1. Publisher

Publisher реализован внутри FastAPI приложения.

Доступные endpoint'ы:

- `POST /predict` — создать ML-задачу и отправить её в RabbitMQ
- `GET /predict/{task_id}` — получить статус и результат задачи
- `GET /models` — получить список доступных моделей

### 2. RabbitMQ

RabbitMQ развёрнут через Docker Compose.

Используется:

- один broker
- одна очередь `ml_task_queue`
- стандартный exchange (`exchange=""`)
- режим один publisher — несколько consumers

### 3. ML-воркеры

Подняты два воркера:

- `worker-1`
- `worker-2`

Оба воркера подписаны на одну очередь и получают сообщения по схеме round-robin.

Каждый воркер:

- получает сообщение из очереди
- извлекает `task_id`
- валидирует `features`
- выполняет mock ML-predict
- записывает результат в PostgreSQL
- сохраняет `worker_id` и статус обработки

---

## Формат сообщения

~~~json
{
  "task_id": "uuid",
  "features": {
    "x1": 1.2,
    "x2": 5.7
  },
  "model": "demo_model",
  "timestamp": "2026-01-01T12:00:00"
}
~~~

---

## Формат результата обработки

~~~json
{
  "task_id": "uuid",
  "prediction": 6.9,
  "worker_id": "worker-1",
  "status": "success"
}
~~~

---

## Структура проекта

├── app
│   ├── src
│   │   ├── routers
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── balance.py
│   │   │   ├── history.py
│   │   │   ├── predict.py
│   │   │   ├── system.py
│   │   │   └── users.py
│   │   ├── __init__.py
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
│   │   └── worker.py
│   ├── tests
│   │   └── test_task4_api.py
│   ├── .env
│   ├── .env example
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── web-proxy
│   └── nginx.conf
├── .gitignore
├── 1.py
├── docker-compose.yml
├── README.md
└── repo_dump.txt

---

## Запуск проекта

Сначала удалить volume:

~~~bash
docker compose down -v
~~~

Далее запустить проект:

~~~bash
docker compose up --build
~~~

---

## Проверка сервисов

### Swagger

~~~text
http://localhost/docs
~~~

### RabbitMQ Management UI

~~~text
http://localhost:15672
~~~


---

## Демо-модель

Для демонстрации используется модель:

- `demo_model`

Mock-предикт рассчитывается как сумма всех числовых признаков.

Пример:

- `x1 = 1.2`
- `x2 = 5.7`

Результат:

- `prediction = 6.9`

---

## Примеры запросов

### Регистрация пользователя

~~~bash
curl -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "login": "new_user",
    "email": "new_user@mail.com",
    "password": "123456"
  }'
~~~

### Авторизация

~~~bash
curl -X POST http://localhost/auth/login \
  -u new_user:123456
~~~

### Получить список моделей

~~~bash
curl http://localhost/models \
  -u new_user:123456
~~~

### Создать ML-задачу

~~~bash
curl -X POST http://localhost/predict \
  -u new_user:123456 \
  -H "Content-Type: application/json" \
  -d '{
    "model": "demo_model",
    "features": {
      "x1": 1.2,
      "x2": 5.7
    }
  }'
~~~

Пример ответа:

~~~json
{
  "task_id": "ec8d4b3e-8f67-4ae4-9fde-c3e69c06285f",
  "status": "new"
}
~~~

### Проверить статус задачи

~~~bash
curl http://localhost/predict/ec8d4b3e-8f67-4ae4-9fde-c3e69c06285f \
  -u new_user:123456
~~~

### Получить историю задач

~~~bash
curl http://localhost/history/predictions \
  -u new_user:123456
~~~

---

## Ручное тестирование

Вручную проверено:

- создание задач через `POST /predict`
- появление сообщений в RabbitMQ
- обработка задач двумя воркерами
- распределение задач между `worker-1` и `worker-2`
- сохранение результата обработки в PostgreSQL
- получение результата через `GET /predict/{task_id}`
- запрет на просмотр чужой задачи (`403 Forbidden`)

---

## Логи воркеров

Для проверки распределения задач между воркерами можно использовать:

~~~bash
docker compose logs -f worker-1
~~~

~~~bash
docker compose logs -f worker-2
~~~

---

## Запуск тестов

~~~bash
docker compose exec app python -m pytest -q tests
~~~

---