import os
import sys
from decimal import Decimal

import pytest

# task_1 в путь
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from domain_model import (
    Admin,
    User,
    UserBalance,
    SimpleModel,
    Task,
    NotEnoughMoneyError,
    TaskStatus,
)


# проверка что админ может пополнить баланс
def test_admin_add_money():
    admin = Admin(1, "admin@mail.com", Admin.make_password_hash("123"))
    user = User(2, "user@mail.com", User.make_password_hash("456"))
    balance = UserBalance(user_id=user.id)

    admin.add_money_user(balance, Decimal("100"))

    assert balance.get_amount() == Decimal("100")


# проверка что задача нормально запускается
def test_task_run_ok():
    user = User(1, "user@mail.com", User.make_password_hash("123"))
    balance = UserBalance(user_id=user.id, amount=Decimal("50"))

    model = SimpleModel(
        model_id=1,
        name="test model",
        description="simple",
        price=Decimal("25")
    )

    data = [
        {"value": 5},
        {"value": 12},
        {"name": "bad row"}
    ]

    task = Task(1, user, balance, model, data)
    result = task.run()

    assert task.get_status() == TaskStatus.DONE
    assert balance.get_amount() == Decimal("25")
    assert len(result.get_answers()) == 2
    assert len(task.get_errors()) == 1


# проверка что если денег мало, будет ошибка
def test_task_run_no_money():
    user = User(1, "user@mail.com", User.make_password_hash("123"))
    balance = UserBalance(user_id=user.id, amount=Decimal("10"))

    model = SimpleModel(
        model_id=1,
        name="test model",
        description="simple",
        price=Decimal("25")
    )

    data = [{"value": 7}]

    task = Task(1, user, balance, model, data)

    with pytest.raises(NotEnoughMoneyError):
        task.run()