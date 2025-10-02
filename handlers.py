import asyncio
from aiogram import Router, F, types, Bot
from aiogram.types import Message, FSInputFile, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction
import os
from aiogram.fsm.context import FSMContext
import uuid
import contextlib
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.enums import ContentType
from states import Chat, Images
import keyboards as kb
from generategpt import GPT_text, GPT_vision
from datetime import datetime
from db import (
    AsyncSessionLocal, get_or_create_user,
    ensure_access_with_wallet_daily, get_balance, credit_balance,
    is_subscription_active,
    reward_referrer_on_first_paid,
    ensure_access_with_wallet_daily,
    DAILY_PRICE_KOP, MONTH_PRICE_RUB, set_inviter_if_first)

router = Router()

async def push_state(state: FSMContext, new_state):
    # Сохраняем текущий state в стек, затем переключаемся в новый
    cur = await state.get_state()
    data = await state.get_data()
    stack = data.get('state_stack', [])
    if cur:
        stack.append(cur)
        await state.update_data(state_stack=stack)
    await state.set_state(new_state)

async def pop_state(state: FSMContext):
    # Возвращаемся в предыдущий state, если он был; иначе чистим
    data = await state.get_data()
    stack = data.get('state_stack', [])
    if stack:
        prev = stack.pop()
        await state.update_data(state_stack=stack)
        await state.set_state(prev)
        return prev
    await state.clear()
    return None

@router.message(Images.photo, F.photo)
async def photo_received(message: Message, state: FSMContext):
    # сохраняем фото во временный файл и кладём путь в FSM
    file_name = f"{uuid.uuid4()}.jpg"
    await message.bot.download(message.photo[-1], destination=file_name)
    await state.update_data(photo_path=file_name)

    # спрашиваем про доп.данные
    await state.set_state(Images.meta)
    await message.answer(
        "Можешь уточнить состав и граммовку или нажми «Пропустить».", reply_markup=kb.photo_extra)

@router.message(Images.wait)
async def wait_wait(message: Message):
    await message.answer('Ваше изображение обрабатывается, подождите...')

@router.message(Chat.wait)
async def wait_wait(message: Message):
    await message.answer('Ваше сообщение генерируется, подождите...')

@router.callback_query(F.data == 'back')
async def back(callback: CallbackQuery, state: FSMContext):
    # чистим состояния, чтобы не застрять
    await state.clear()
    # возвращаем пользователя в экран "Пользоваться ботом"
    await callback.message.edit_text(
        "Выберите пункт меню, чтобы пользоваться ботом.",
        reply_markup=kb.inline_main
    )


@router.callback_query(F.data == 'guide')
async def guide(callback: CallbackQuery):
    text = (
        "ℹ️ Как пользоваться ботом:\n\n"
        "1️⃣  Загрузить фото (подсчёт КБЖУ)\n"
        "Отправь фото блюда, и бот рассчитает примерное содержание калорий, белков, жиров и углеводов.\n\n"
        "2️⃣  ИИ ассистент\n"
        "Задавай вопросы про тренировки, питание, диеты и здоровый образ жизни.\n"
        "Например:\n"
        "- Как составить план тренировок для набора мышц?\n"
        "- Какие продукты лучше включить в рацион для похудения?\n"
        "- Как распределить приёмы пищи в течение дня?\n\n"
        "❌ Если вопрос не по теме (например, про политику или погоду), бот напомнит, "
        "что он отвечает только по тренировкам, питанию и ЗОЖ.\n\n"
        "3️⃣  Кнопка «Назад»\n"
        "Позволяет отменить действие."
    )
    await callback.message.edit_text(text, reply_markup=kb.menu_return)

# вернуть пользователя к обычному режиму (3 кнопки)
@router.callback_query(F.data == 'use_bot')
async def use_bot(cb: CallbackQuery):
    await cb.message.edit_text("Выберите пункт меню, чтобы пользоваться ботом.", reply_markup=kb.inline_main)

# Техподдержка — вариант 1: показать контакты (коллбэк)
@router.callback_query(F.data == 'support')
async def support(cb: CallbackQuery):
    await cb.message.edit_text(
        "🛟 Техподдержка\n\n"
        "Напишите нам: @your_support_username\n"
        "Email: support@example.com\n\n"
        "Вернитесь в главное меню кнопкой ниже.",
        reply_markup=kb.pay_actions
    )

@router.message(Chat.text)
async def chat_response(message: Message, state: FSMContext):
    await message.bot.send_chat_action(chat_id=message.from_user.id, action=ChatAction.TYPING)
    await state.set_state(Chat.wait)
    resp = await GPT_text(message.text)
    await message.answer(resp, reply_markup=kb.inline_main)
    await state.clear()


@router.callback_query(F.data == 'skip_photo_meta')
async def skip_photo_meta(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    file_name = data.get("photo_path")
    await cb.message.bot.send_chat_action(chat_id=cb.from_user.id, action=ChatAction.TYPING)
    await cb.message.edit_text("Обрабатываю фото… ⏳")
    try:
        await state.set_state(Images.wait)
        resp = await GPT_vision(file_name, extra_text=None)
        await cb.message.edit_text(resp, reply_markup=kb.inline_main)
    finally:
        with contextlib.suppress(Exception):
            os.remove(file_name)
        await state.clear()

@router.message(Images.meta, F.text)
async def photo_with_meta(message: Message, state: FSMContext):
    data = await state.get_data()
    file_name = data.get("photo_path")
    user_extra = message.text.strip()
    await message.bot.send_chat_action(chat_id=message.from_user.id, action=ChatAction.TYPING)

    status_msg = await message.answer("Обрабатываю фото с учётом твоих данных… ⏳")
    try:
        await state.set_state(Images.wait)
        resp = await GPT_vision(file_name, extra_text=user_extra)
        await status_msg.edit_text(resp, reply_markup=kb.inline_main)
    finally:
        with contextlib.suppress(Exception):
            os.remove(file_name)
        await state.clear()


async def _status_line(tg_id: int) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, tg_id)
        paid_today = (user.last_charge_date == today)
        sub_active = await is_subscription_active(session, tg_id)
        bal = await get_balance(session, tg_id)
    need_rub = (DAILY_PRICE_KOP + 99) // 100  # 3 ₽ при DAILY_PRICE_KOP=300
    allowed = sub_active or paid_today or (bal >= need_rub)
    return "🟢 Доступ: оплачен" if allowed else "🔴 Доступ не оплачен"

@router.callback_query(F.data == 'menu')
async def show_main_menu(cb: CallbackQuery):
    status_block = await _status_line(cb.from_user.id)
    text = (
        "📋 Главное меню\n\n"
        f"{status_block}\n\n"
        "💳 Баланс и пополнение → кнопка «Оплата»»\n"
        "ℹ️ Как пользоваться ботом → кнопка «Инструкция»"
    )
    await cb.message.edit_text(text, reply_markup=kb.inline_menu)

@router.pre_checkout_query()
async def process_pre_checkout(pre: PreCheckoutQuery, bot: Bot):
    # Тут можно делать свои проверки payload/цены при желании.
    await bot.answer_pre_checkout_query(pre.id, ok=True)

from aiogram.filters.command import CommandObject

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject | None = None):
    # 1) обработаем дип-ссылку /start ref_<tgid>
    try:
        arg = (command.args or "").strip() if command else ""
        if arg.startswith("ref_"):
            inviter_tg = int(arg.replace("ref_", "").strip())
            async with AsyncSessionLocal() as session:
                await set_inviter_if_first(session, invitee_tg=message.from_user.id, inviter_tg=inviter_tg)
    except Exception:
        pass

    # 2) остальной твой код
    await message.bot.send_chat_action(chat_id=message.from_user.id, action=ChatAction.TYPING)
    await asyncio.sleep(0.2)

    user_name = message.from_user.first_name
    status_block = await _status_line(message.from_user.id)

    await message.answer(
        f"""Привет, {user_name}! 👋 
Я могу: 
- Посчитать КБЖУ по фото блюда
- Дать советы по питанию 
- Подсказать по тренировкам и фитнесу
- Ответить на твои вопросы про здоровье и спорт

{status_block}

💳 Баланс и пополнение → кнопка «Оплата»
ℹ️ Как пользоваться ботом → кнопка «Инструкция»
▶️ Чтобы начать пользоваться ботом, нажми «Пользоваться ботом»
""",
        reply_markup=kb.inline_menu
    )

@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment_handler(message: Message):
    sp = message.successful_payment
    payload = sp.invoice_payload or ""
    total_rub = (sp.total_amount or 0) // 100
    tg_id = message.from_user.id

    # тут у нас только пополнение
    if payload.startswith("topup_"):
        async with AsyncSessionLocal() as session:
            # зачисляем пользователю
            new_balance = await credit_balance(session, tg_id, total_rub)
            # раздаём реферал-бонус пригласившему (однократно — логика внутри)
            await reward_referrer_on_first_paid(session, invitee_tg=tg_id)

        await message.answer(
            "✅ Оплата прошла успешно.\n"
            f"Зачислено: {total_rub} ₽\n"
            f"Текущий баланс: {new_balance} ₽", reply_markup=kb.pay_result_kb
        )
    else:
        # на всякий случай
        async with AsyncSessionLocal() as session:
            bal = await get_balance(session, tg_id)
        await message.answer(f"✅ Платёж успешен. Баланс: {bal} ₽")

        status_line = await _status_line(tg_id)
        await message.answer(
            f"📋 Главное меню\n\n{status_line}",
            reply_markup=kb.inline_menu
        )

@router.callback_query(F.data == 'referrals')
async def referrals(cb: CallbackQuery):
    my_tg = cb.from_user.id
    me = await cb.message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{my_tg}"

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, my_tg)
        balance = user.balance_rub or 0

    await cb.message.edit_text(
        "Реферальная программа\n\n"
        f"Ваша личная ссылка: {link}\n"
        "За каждого приглашённого, кто оплатит подписку, вы получаете +50 ₽ на баланс.\n\n"
        f"Текущий баланс: {balance} ₽",
        reply_markup=kb.ref_menu
    )

@router.callback_query(F.data == 'assistant')
async def assistant(callback: CallbackQuery, state: FSMContext):
    status = await ensure_access_with_wallet_daily(callback.from_user.id)
    if not status["allowed"]:
        await callback.message.edit_text(
            "Недостаточно средств на балансе.\n"
            "Пополните баланс на 100 ₽ (в разделе «Оплата»), чтобы пользоваться ботом.",
            reply_markup=kb.pay_actions
        )
        return
    await push_state(state, Chat.text)
    await callback.message.answer('Напиши свой вопрос про питание, диету или тренировки 👇', reply_markup=kb.back_main)

@router.callback_query(F.data == 'upload_photo')
async def upload_photo(callback: CallbackQuery, state: FSMContext):
    status = await ensure_access_with_wallet_daily(callback.from_user.id)
    if not status["allowed"]:
        await callback.message.edit_text(
            "Недостаточно средств на балансе.\n"
            "Пополните баланс на 100 ₽ (в разделе «Оплата»), чтобы пользоваться ботом.",
            reply_markup=kb.pay_actions
        )
        return
    await state.set_state(Images.photo)
    await callback.message.edit_text('Отправь фото блюда, я посчитаю КБЖУ.', reply_markup=kb.back_main)

@router.callback_query(F.data == 'sub_buy')
async def sub_buy(cb: CallbackQuery):
    async with AsyncSessionLocal() as session:
        bal = await get_balance(session, cb.from_user.id)

    daily_rub = DAILY_PRICE_KOP / 100
    text = (
        "💳 Оплата и баланс\n\n"
        f"Текущий баланс: {bal} ₽\n\n"
        "План: 1 месяц доступа ко всем функциям бота.\n"
        f"Стоимость: {os.getenv('SUB_PRICE_RUB', '100')} ₽ в месяц.\n\n"
        "Нажмите «Оплатить», чтобы оформить подписку"
    )
    await cb.message.edit_text(text, reply_markup=kb.pay_actions)  # pay_actions теперь с одной кнопкой «Пополнить 100 ₽»

@router.callback_query(F.data == 'topup_100')
async def topup_100(cb: CallbackQuery):
    prices = [LabeledPrice(label="Пополнение баланса", amount=100 * 100)]
    await cb.message.answer_invoice(
        title="Пополнение баланса",
        description="Зачисление 100 ₽ на баланс бота",
        payload=f"topup_{cb.from_user.id}",
        provider_token=os.getenv("PAYMENT_PROVIDER_TOKEN", ""),
        currency="RUB",
        prices=prices,
        need_name=False, need_phone_number=False, need_email=False,
        need_shipping_address=False, is_flexible=False
    )

@router.callback_query(F.data == 'pay_now')
async def pay_now(cb: CallbackQuery):
    amount_rub = int(os.getenv("SUB_PRICE_RUB", "100"))
    prices = [LabeledPrice(label="Месячная подписка (30 дней)", amount=amount_rub * 100)]
    await cb.message.answer_invoice(
        title="Подписка на 1 месяц",
        description="Доступ ко всем функциям бота на 30 дней",
        payload=f"sub_month_{cb.from_user.id}",
        provider_token=os.getenv("PAYMENT_PROVIDER_TOKEN", ""),
        currency="RUB",
        prices=prices,
        need_name=False, need_phone_number=False, need_email=False,
        need_shipping_address=False, is_flexible=False
    )
