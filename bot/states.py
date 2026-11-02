from aiogram.fsm.state import State, StatesGroup


class NewReq(StatesGroup):
    title = State()
    amount = State()
    currency = State()
    date = State()
    comment = State()
    field = State()
    confirm = State()


class EditReq(StatesGroup):
    value = State()


class RejectReq(StatesGroup):
    reason = State()


class AddField(StatesGroup):
    name = State()
    type = State()
    options = State()
    required = State()


class RenameField(StatesGroup):
    name = State()


class EditOptions(StatesGroup):
    options = State()


class AddCurrency(StatesGroup):
    code = State()
