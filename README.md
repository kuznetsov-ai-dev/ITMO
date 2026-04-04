# Задание 2

Структура проекта и Docker Compose.

## Задача

Нужно организовать структуру backend-проекта и описать структуру приложения через docker-compose.

**В проекте подготовлены 4 сервиса:**

- `app` — backend-приложение
- `web-proxy` — proxy на Nginx
- `rabbitmq` — брокер сообщений
- `database` — база данных PostgreSQL

## Структура проекта

```text
ITMO/
├── app/
    ├── src/
│   ├── .env
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── data/
│   └── rabbitmq/
│       └── .gitkeep
├── task_1/
│   ├── domain_model.py
│   ├── main.py
│   ├── README.md
│   └── test/
│       └── test_domain_model.py
├── web-proxy/
│   └── nginx.conf
├── docker-compose.yml
├── README.md
└── .gitignore
```


**Основные требования, которые выполнены**

- создано 4 сервиса
- app настроен через env_file
- исходники app подключаются через volumes
- app не пробрасывает порты наружу
- web-proxy работает на Nginx
- web-proxy зависит от app
- web-proxy пробрасывает порты 80 и 443
- rabbitmq пробрасывает порты 5672 и 15672
- для rabbitmq настроено хранение данных через volume
- у rabbitmq включен автоматический перезапуск
- database работает на образе postgres
- для database настроено сохранение данных через named volume

