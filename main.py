from decimal import Decimal
from domain_model import Admin, User, UserBalance, SimpleModel, Task


# тут базовый вариант
def main() -> None:
    # создаем админа и обычного пользователя
    admin = Admin(
        1,
        "admin@mail.com",
        Admin.make_password_hash("123")
    )

    user = User(
        2,
        "user@mail.com",
        User.make_password_hash("456")
    )

    # создаем отдельную сущность баланса пользователя
    user_balance = UserBalance(user_id=user.id)

    # админ пополняет баланс пользователю
    admin.add_money_user(user_balance, Decimal("100"))

    # создаем простую модель
    model = SimpleModel(
        model_id=1,
        name="prostaya model",
        description="uchebnaya model dlya dz",
        price=Decimal("25")
    )

    # данные для задачи
    data = [
        {"value": 5},
        {"value": 12},
        {"name": "stroka bez nuzhnogo polya"},
        {"value": "text"},
        {"value": 20}
    ]

    # создаем задачу
    task = Task(
        task_id=1,
        user=user,
        balance=user_balance,
        model=model,
        data=data
    )

    # запускаем задачу
    result = task.run()

    # в консоль
    print("Статус задачи:", task.get_status().value)
    print("Баланс пользователя:", user_balance.get_amount())
    print()

    print("Ответы модели:")
    for item in result.get_answers():
        print(item)
    print()

    print("Ошибки в данных:")
    for err in task.get_errors():
        print(err)
    print()

    print("Короткий итог:")
    print(result.get_info())


if __name__ == "__main__":
    main()