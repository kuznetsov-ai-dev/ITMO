# Задание 5. Взаимодействие с ML-сервисом через RabbitMQ

## Описание

В проекте реализовано асинхронное взаимодействие с ML-сервисом через RabbitMQ.

Система построена по схеме:

- один publisher — FastAPI приложение
- один broker — RabbitMQ
- одна очередь `ml_task_queue`
- два consumers — `worker-1` и `worker-2`

FastAPI принимает входящий запрос, формирует ML-задачу, сохраняет её в PostgreSQL и отправляет сообщение в очередь RabbitMQ.

Воркеры получают задачи из очереди, валидируют входные данные, выполняют учебный ML-predict и сохраняют результат обработки в базе данных.

---

## Реализованные компоненты

### 1. Publisher

Publisher реализован внутри FastAPI приложения.

Доступные endpoint'ы:

- `POST /predict` — создать ML-задачу и отправить её в RabbitMQ
- `GET /predict/{task_id}` — получить статус и результат задачи
- `GET /models` — получить список доступных моделей


При создании задачи система до отправки в RabbitMQ проверяет баланс пользователя.
Если средств недостаточно, запрос сразу завершается ошибкой и задача не отправляется в очередь.

Если средств достаточно, стоимость модели списывается сразу и создаётся транзакция типа `charge`.
Если обработка задачи завершится ошибкой, пользователю автоматически создаётся возврат средств через транзакцию типа `deposit`.

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
- выполняет учебный ML-predict
- записывает результат в PostgreSQL
- сохраняет `worker_id` и статус обработки

---

## Формат сообщения

~~~json
{
  "task_id": "uuid",
  "features": {
    "value": 12
  },
  "model": "simple-quality-model",
  "timestamp": "2026-01-01T12:00:00"
}
~~~

---

## Формат результата обработки

~~~json
{
  "task_id": "uuid",
  "worker_id": "worker-1",
  "status": "success",
  "prediction": "хорошо",
  "value": 12.0,
  "threshold": 10.0
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

## Учебная модель

Для демонстрации используется модель:

- `simple-quality-model`

Логика модели:

- обязателен числовой признак `value`
- если `value >= 10`, модель возвращает `prediction = "хорошо"`
- если `value < 10`, модель возвращает `prediction = "плохо"`

Пример:

- `value = 12`

Результат:

- `prediction = "хорошо"`
- `threshold = 10.0`

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
    "model": "simple-quality-model",
    "features": {
      "value": 12
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

После создания задачи стоимость модели списывается сразу.
Для `simple-quality-model` при начальном балансе `100.00` баланс пользователя станет `75.00`.

### Проверить статус задачи

~~~bash
curl http://localhost/predict/ec8d4b3e-8f67-4ae4-9fde-c3e69c06285f \
  -u new_user:123456
~~~


Пример успешного результата:

~~~json
{
  "id": 1,
  "task_id": "ec8d4b3e-8f67-4ae4-9fde-c3e69c06285f",
  "user_id": 4,
  "model_id": 1,
  "model_name": "simple-quality-model",
  "status": "done",
  "worker_id": "worker-1",
  "charged_amount": "25.00",
  "total_rows": 1,
  "valid_rows": 1,
  "invalid_rows": 0,
  "result_payload": {
    "task_id": "ec8d4b3e-8f67-4ae4-9fde-c3e69c06285f",
    "worker_id": "worker-1",
    "status": "success",
    "prediction": "хорошо",
    "value": 12.0,
    "threshold": 10.0
  }
}
~~~


### Получить историю задач

~~~bash
curl http://localhost/history/predictions \
  -u new_user:123456
~~~

---

## Ручное тестирование

Вручную проверено:

- отказ в создании задачи при недостатке средств (`insufficient_funds`) до RabbitMQ
- списание стоимости модели при создании задачи
- обработка задач двумя воркерами
- распределение задач между `worker-1` и `worker-2`
- сохранение результата обработки в PostgreSQL
- получение результата через `GET /predict/{task_id}`
- автоматический возврат средств при ошибке обработки
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