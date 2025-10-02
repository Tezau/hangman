# db.py
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Integer, String, BigInteger, DateTime, ForeignKey, func, select, Boolean
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# ---------- Константы/настройки ----------
DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///bot.db")

# Цена «в день» в копейках (по умолчанию 300 = 3 ₽/день, чтобы не работать с дробями)
DAILY_PRICE_KOP = int(os.getenv("DAILY_PRICE_KOP", "300"))

# Цена месячной подписки, используется для интерфейса/оплаты
MONTH_PRICE_RUB = int(os.getenv("SUB_PRICE_RUB", "100"))

# Кол-во бесплатных попыток в месяц


# Бонус за приглашённого оплатившего реферала (в рублях)
REFERRAL_BONUS_RUB = int(os.getenv("REFERRAL_BONUS_RUB", "50"))

# ---------- SQLAlchemy ----------
engine = create_async_engine(DB_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# ---------- Модели ----------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    # баланс в РУБЛЯХ (целое), пополняем на 100, списываем округлением вверх из копеек
    balance_rub: Mapped[int] = mapped_column(Integer, default=0)
    # дата последнего списания дневной оплаты (YYYY-MM-DD, строкой для простоты)
    last_charge_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # реферальные поля
    inviter_tg: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    first_payment_bonus_given: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    start_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")

# ---------- Инициализация ----------
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------- Вспомогательные ----------
def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

# ---------- Публичные функции, которые дергает handlers.py ----------
async def get_or_create_user(session: AsyncSession, tg_id: int) -> User:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    user = res.scalar_one_or_none()
    if not user:
        user = User(tg_id=tg_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_balance(session: AsyncSession, tg_id: int) -> int:
    user = await get_or_create_user(session, tg_id)
    return user.balance_rub or 0


async def credit_balance(session: AsyncSession, tg_id: int, amount_rub: int) -> int:
    user = await get_or_create_user(session, tg_id)
    user.balance_rub = (user.balance_rub or 0) + int(amount_rub)
    await session.commit()
    return user.balance_rub


async def _active_subscription_until(session: AsyncSession, user_id: int) -> Optional[datetime]:
    res = await session.execute(
        select(func.max(Subscription.end_at)).where(Subscription.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def is_subscription_active(session: AsyncSession, tg_id: int) -> bool:
    user = await get_or_create_user(session, tg_id)
    end = await _active_subscription_until(session, user.id)
    return bool(end and end.date() >= datetime.utcnow().date())


async def activate_subscription(session: AsyncSession, user_id: int, days: int = 30) -> Subscription:
    current_end = await _active_subscription_until(session, user_id)
    start_from = max(datetime.utcnow(), current_end) if current_end else datetime.utcnow()
    sub = Subscription(
        user_id=user_id,
        start_at=datetime.utcnow(),
        end_at=start_from + timedelta(days=days),
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def ensure_access_with_wallet_daily(tg_id: int) -> dict:
    """
    Правило доступа (без пробных попыток):
    1) Если активна подписка — доступ есть.
    2) Если сегодня уже списано — доступ есть.
    3) Иначе пытаемся списать стоимость дня (округление вверх). Если хватило — доступ есть.
    4) Иначе — доступа нет.
    """
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, tg_id)

        # 1) активная подписка?
        if await is_subscription_active(session, tg_id):
            return {"allowed": True, "reason": "sub_active"}

        # 2) уже списывали сегодня?
        today = _today_str()
        if user.last_charge_date == today:
            return {"allowed": True, "reason": "already_charged"}

        # 3) пробуем списать дневную стоимость (3 ₽ при DAILY_PRICE_KOP=300)
        rub_to_charge = (DAILY_PRICE_KOP + 99) // 100
        if (user.balance_rub or 0) >= rub_to_charge:
            user.balance_rub -= rub_to_charge
            user.last_charge_date = today
            await session.commit()
            return {"allowed": True, "reason": "charged"}

        # 4) денег нет — доступ закрыт
        return {"allowed": False, "reason": "no_balance"}

async def set_inviter_if_first(session: AsyncSession, invitee_tg: int, inviter_tg: int) -> bool:
    """Сохраняем пригласившего один раз, игнорируем самоприглашение."""
    if invitee_tg == inviter_tg:
        return False
    user = await get_or_create_user(session, invitee_tg)
    if user.inviter_tg is None:
        user.inviter_tg = inviter_tg
        await session.commit()
        return True
    return False


async def reward_referrer_on_first_paid(session: AsyncSession, invitee_tg: int) -> None:
    """Начисляем бонус пригласившему один раз при первой оплате приглашённого."""
    user = await get_or_create_user(session, invitee_tg)
    if user.inviter_tg and not user.first_payment_bonus_given:
        inviter = await get_or_create_user(session, user.inviter_tg)
        inviter.balance_rub = (inviter.balance_rub or 0) + REFERRAL_BONUS_RUB
        user.first_payment_bonus_given = True
        await session.commit()
