from aiogram.fsm.state import StatesGroup, State


class Chat(StatesGroup):
    text = State()
    wait = State()

class Images(StatesGroup):
    photo = State()
    wait = State()
    meta = State()
