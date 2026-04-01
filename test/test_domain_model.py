import os
import sys
from decimal import Decimal

import pytest

# чтобы видеть domain_model.py
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from domain_model import Admin, User, SimpleModel, Task, NotEnoughMoneyError, TaskStatus


# проверка что админ может пополнить баланс
def test_admin_add_money():
    admin = Admin(1, "admin@mail.com", "123")
    user = User(2, "user@mail.com", "456")

    admin.add_money_user(user, Decimal("100"))

    assert user.get_balance() == Decimal("100")


# проверка что задача нормально запускается
def test_task_run_ok():
    user = User(1, "user@mail.com", "123", balance=Decimal("50"))

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

    task = Task(1, user, model, data)
    result = task.run()

    assert task.get_status() == TaskStatus.DONE
    assert user.get_balance() == Decimal("25")
    assert len(result.get_answers()) == 2
    assert len(task.get_errors()) == 1


# проверка что если денег мало, будет ошибка
def test_task_run_no_money():
    user = User(1, "user@mail.com", "123", balance=Decimal("10"))

    model = SimpleModel(
        model_id=1,
        name="test model",
        description="simple",
        price=Decimal("25")
    )

    data = [{"value": 7}]

    task = Task(1, user, model, data)

    with pytest.raises(NotEnoughMoneyError):
        task.run()