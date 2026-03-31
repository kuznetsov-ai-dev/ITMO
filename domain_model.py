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

    # чтобы удобно печатать ошибку
    def __str__(self) -> str:
        return f"строка {self.row_num}, поле '{self.field_name}': {self.text}"


# базовый класс для движения денег
class MoneyMove:
    # тут общие поля для любой операции с деньгами
    def __init__(
        self,
        move_id: int,
        user: "User",
        amount: Decimal,
        task_id: int | None = None
    ) -> None:
        self.id = move_id
        self._user = user
        self._amount = amount
        self._task_id = task_id
        self._created_at = datetime.now()

    # вернуть сумму операции
    def get_amount(self) -> Decimal:
        return self._amount

    # этот метод должны переопределить наследники
    def do(self) -> None:
        raise NotImplementedError("Метод do() не переопределен")


# операция пополнения
class PlusMoney(MoneyMove):
    # прибавляет к балансу
    def do(self) -> None:
        self._user._plus_balance(self._amount)


# операция списания
class MinusMoney(MoneyMove):
    # убавляет от баланса
    def do(self) -> None:
        self._user._minus_balance(self._amount)


# обычный пользователь
class User:
    # создаем пользователя
    def __init__(
        self,
        user_id: int,
        email: str,
        password: str,
        role: UserRole = UserRole.USER,
        balance: Decimal = Decimal("0")
    ) -> None:
        self.id = user_id
        self._email = email
        self._password = password
        self._role = role
        self._balance = balance
        self._moves: list[MoneyMove] = []

    # вернуть почту
    def get_email(self) -> str:
        return self._email

    # вернуть роль
    def get_role(self) -> UserRole:
        return self._role

    # вернуть баланс
    def get_balance(self) -> Decimal:
        return self._balance

    # вернуть историю операций
    def get_moves(self) -> list[MoneyMove]:
        return self._moves.copy()

    # хватает ли денег
    def has_money(self, amount: Decimal) -> bool:
        return self._balance >= amount

    # пополнить баланс
    def add_money(self, amount: Decimal) -> PlusMoney:
        move = PlusMoney(
            move_id=len(self._moves) + 1,
            user=self,
            amount=amount
        )
        move.do()
        self._moves.append(move)
        return move

    # списать деньги
    def take_money(self, amount: Decimal, task_id: int | None = None) -> MinusMoney:
        if not self.has_money(amount):
            raise NotEnoughMoneyError("На балансе мало денег")

        move = MinusMoney(
            move_id=len(self._moves) + 1,
            user=self,
            amount=amount,
            task_id=task_id
        )
        move.do()
        self._moves.append(move)
        return move

    # внутренняя функция пополнения
    def _plus_balance(self, amount: Decimal) -> None:
        self._balance += amount

    # внутренняя функция списания
    def _minus_balance(self, amount: Decimal) -> None:
        self._balance -= amount


# далее сразу админ