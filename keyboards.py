from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

main = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='📸 Загрузить фото (подсчёт калорий)'), KeyboardButton(text='Чат дцп')],
],
                           resize_keyboard=True,
                           input_field_placeholder='Выберите пункт меню.')

inline_main = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='📸 Загрузить фото (подсчёт КБЖУ)', callback_data='upload_photo')],
    [InlineKeyboardButton(text='🤖 ИИ ассистент', callback_data='assistant')],
    [InlineKeyboardButton(text='📋 Главное меню', callback_data='menu')]
])

inline_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='💳 Оплата', callback_data='sub_buy')],
    [InlineKeyboardButton(text='ℹ️ Инструкция', callback_data='guide')],
    [InlineKeyboardButton(text='🎁 Рефералы', callback_data='referrals')],
    [InlineKeyboardButton(text='▶️ Пользоваться ботом', callback_data='use_bot')]
])

back_main = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Назад', callback_data='back')]
    ])

menu_return = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Вернуться', callback_data='menu')]
    ])

photo_extra = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='⏭ Пропустить', callback_data='skip_photo_meta')],
    [InlineKeyboardButton(text='Назад', callback_data='back')]
])

pay_actions = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='💳 Оплатить', callback_data='topup_100')],
    [InlineKeyboardButton(text='🛟 Техподдержка', callback_data='support')],
    [InlineKeyboardButton(text='📋 Главное меню', callback_data='menu')]
])

ref_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='📋 Главное меню', callback_data='menu')]
])

pay_result_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='📋 Главное меню', callback_data='menu')],
    [InlineKeyboardButton(text='▶️ Пользоваться ботом', callback_data='use_bot')]
])