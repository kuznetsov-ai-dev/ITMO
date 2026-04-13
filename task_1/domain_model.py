import hashlib
from decimal import Decimal
from datetime import datetime
from enum import Enum


# роль пользователя
class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"


# статус задачи
class TaskStatus(Enum):
    NEW = "new"
    WORK = "work"
    DONE = "done"
    ERROR = "error"


# ошибка если денег мало
class NotEnoughMoneyError(Exception):
    pass


# ошибка если задачу запустили не в том статусе
class BadTaskStatusError(Exception):
    pass


# ошибка в одной строке данных
class DataError:
    # сохраняем номер строки, поле и текст ошибки
    def __init__(self, row_num: int, field_name: str, text: str) -> None:
        self.row_num = row_num
        self.field_name = field_name
        self.text = text

    # печать ошибки
    def __str__(self) -> str:
        return f"строка {self.row_num}, поле '{self.field_name}': {self.text}"


# базовый класс для движения денег
class MoneyMove:
    # тут общие поля для любой операции с деньгами
    def __init__(
        self,
        move_id: int,
        user_id: int,
        amount: Decimal,
        task_id: int | None = None
    ) -> None:
        self.id = move_id
        self._user_id = user_id
        self._amount = amount
        self._task_id = task_id
        self._created_at = datetime.now()

    # вернуть id пользователя
    def get_user_id(self) -> int:
        return self._user_id

    # вернуть сумму операции
    def get_amount(self) -> Decimal:
        return self._amount

    # этот метод должны переопределить наследники
    def do(self, balance: "UserBalance") -> None:
        raise NotImplementedError("Метод do() не переопределен")


# операция пополнения
class PlusMoney(MoneyMove):
    # прибавляет к балансу
    def do(self, balance: "UserBalance") -> None:
        balance._plus(self._amount)


# операция списания
class MinusMoney(MoneyMove):
    # убавляет от баланса
    def do(self, balance: "UserBalance") -> None:
        balance._minus(self._amount)


# отдельная сущность баланса пользователя
class UserBalance:
    # баланс связан с пользователем по user_id # поправил
    def __init__(
        self,
        user_id: int,
        amount: Decimal = Decimal("0")
    ) -> None:
        self._user_id = user_id
        self._amount = amount
        self._moves: list[MoneyMove] = []

    # вернуть id пользователя
    def get_user_id(self) -> int:
        return self._user_id

    # вернуть текущий баланс
    def get_amount(self) -> Decimal:
        return self._amount

    # вернуть историю операций
    def get_moves(self) -> list[MoneyMove]:
        return self._moves.copy()

    # хватает ли денег
    def has_money(self, amount: Decimal) -> bool:
        return self._amount >= amount

    # пополнить баланс
    def add_money(self, amount: Decimal) -> PlusMoney:
        move = PlusMoney(
            move_id=len(self._moves) + 1,
            user_id=self._user_id,
            amount=amount
        )
        move.do(self)
        self._moves.append(move)
        return move

    # списать деньги
    def take_money(self, amount: Decimal, task_id: int | None = None) -> MinusMoney:
        if not self.has_money(amount):
            raise NotEnoughMoneyError("На балансе мало денег")

        move = MinusMoney(
            move_id=len(self._moves) + 1,
            user_id=self._user_id,
            amount=amount,
            task_id=task_id
        )
        move.do(self)
        self._moves.append(move)
        return move

    # внутренняя функция пополнения
    def _plus(self, amount: Decimal) -> None:
        self._amount += amount

    # внутренняя функция списания
    def _minus(self, amount: Decimal) -> None:
        self._amount -= amount


# обычный пользователь
class User:
    # создаем пользователя
    def __init__(
        self,
        user_id: int,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER
    ) -> None:
        self.id = user_id
        self._email = email
        self._password_hash = password_hash
        self._role = role

    # сделать хэш пароля
    @staticmethod
    def make_password_hash(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    # вернуть почту
    def get_email(self) -> str:
        return self._email

    # вернуть роль
    def get_role(self) -> UserRole:
        return self._role

    # проверить пароль
    def check_password(self, password: str) -> bool:
        return self._password_hash == self.make_password_hash(password)


# админ
class Admin(User):
    # у админа роль сразу admin
    def __init__(
        self,
        user_id: int,
        email: str,
        password_hash: str
    ) -> None:
        super().__init__(user_id, email, password_hash, UserRole.ADMIN)

    # админ может пополнить баланс пользователя
    def add_money_user(self, balance: UserBalance, amount: Decimal) -> PlusMoney:
        return balance.add_money(amount)

    # админ может посмотреть операции пользователя
    def show_user_moves(self, balance: UserBalance) -> list[MoneyMove]:
        return balance.get_moves()


# базовая модель
class Model:
    # создаем модель
    def __init__(
        self,
        model_id: int,
        name: str,
        description: str,
        price: Decimal,
        active: bool = True
    ) -> None:
        self.id = model_id
        self._name = name
        self._description = description
        self._price = price
        self._active = active

    # вернуть название
    def get_name(self) -> str:
        return self._name

    # вернуть цену
    def get_price(self) -> Decimal:
        return self._price

    # активна модель или нет
    def is_active(self) -> bool:
        return self._active

    # предсказание
    def predict(self, rows: list[dict]) -> list[dict]:
        raise NotImplementedError("Метод predict() не переопределен")


# простая тестовая модель
class SimpleModel(Model):
    # очень простая логика предсказания
    def predict(self, rows: list[dict]) -> list[dict]:
        result = []

        for row in rows:
            new_row = row.copy()
            value = row.get("value", 0)

            if value >= 10:
                new_row["answer"] = "хорошо"
            else:
                new_row["answer"] = "плохо"

            result.append(new_row)

        return result


# результат задачи
class TaskResult:
    # сохраняем итог работы
    def __init__(
        self,
        result_id: int,
        task_id: int,
        answers: list[dict],
        good_count: int,
        bad_count: int,
        price: Decimal
    ) -> None:
        self.id = result_id
        self._task_id = task_id
        self._answers = answers
        self._good_count = good_count
        self._bad_count = bad_count
        self._price = price
        self._created_at = datetime.now()

    # вернуть ответы модели
    def get_answers(self) -> list[dict]:
        return self._answers.copy()

    # короткая инфа по результату
    def get_info(self) -> str:
        return (
            f"задача {self._task_id}, "
            f"валидных строк: {self._good_count}, "
            f"ошибочных строк: {self._bad_count}, "
            f"списано: {self._price}"
        )


# задача для модели
class Task:
    # создаем задачу
    def __init__(
        self,
        task_id: int,
        user: User,
        balance: UserBalance,
        model: Model,
        data: list[dict]
    ) -> None:
        if balance.get_user_id() != user.id:
            raise ValueError("Баланс не принадлежит пользователю")

        self.id = task_id
        self._user = user
        self._balance = balance
        self._model = model
        self._data = data
        self._status = TaskStatus.NEW
        self._created_at = datetime.now()
        self._result: TaskResult | None = None
        self._errors: list[DataError] = []

    # вернуть статус
    def get_status(self) -> TaskStatus:
        return self._status

    # вернуть результат
    def get_result(self) -> TaskResult | None:
        return self._result

    # вернуть ошибки
    def get_errors(self) -> list[DataError]:
        return self._errors.copy()

    # проверка входных данных
    def check_data(self) -> tuple[list[dict], list[DataError]]:
        good_rows = []
        errors = []

        for i, row in enumerate(self._data):
            if "value" not in row:
                errors.append(DataError(i, "value", "нет такого поля"))
            elif not isinstance(row["value"], (int, float)):
                errors.append(DataError(i, "value", "тут должно быть число"))
            else:
                good_rows.append(row)

        self._errors = errors
        return good_rows, errors

    # запуск задачи
    def run(self) -> TaskResult:
        if self._status != TaskStatus.NEW:
            raise BadTaskStatusError("Эту задачу уже нельзя запустить")

        if not self._model.is_active():
            self._status = TaskStatus.ERROR
            raise ValueError("Модель сейчас неактивна")

        price = self._model.get_price()

        if not self._balance.has_money(price):
            self._status = TaskStatus.ERROR
            raise NotEnoughMoneyError("Недостаточно денег для запуска задачи")

        self._status = TaskStatus.WORK

        try:
            good_rows, errors = self.check_data()
            answers = self._model.predict(good_rows)

            self._balance.take_money(price, task_id=self.id)

            result = TaskResult(
                result_id=self.id,
                task_id=self.id,
                answers=answers,
                good_count=len(good_rows),
                bad_count=len(errors),
                price=price
            )

            self._result = result
            self._status = TaskStatus.DONE
            return result

        except Exception:
            self._status = TaskStatus.ERROR
            raise