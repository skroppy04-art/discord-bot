import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from mcrcon import MCRcon
from aiohttp import web
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
RCON_HOST= os.getenv("RCON_HOST")
RCON_PORT= os.getenv("RCON_PORT")
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
# заявки: nick -> данные + user_id
pending = {}
deny_buffer = {}  # для хранения кого отклоняем
RCON_PORT= int(RCON_PORT)
API_SECRET = os.getenv("API_SECRET")

async def create_application(request):
    data = await request.json()

    if data.get("secret") != API_SECRET:
        return web.json_response(
            {"ok": False},
            status=403
        )

    nick = data["nick"]
    age = data["age"]
    source = data["source"]
    goal = data["goal"]

    vk_user_id = data["vk_user_id"]

    pending[nick] = {
        "user_id": vk_user_id,
        "age": age,
        "source": source,
        "goal": goal,
        "platform": "vk"
    }

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✔️ Одобрить",
                    callback_data=f"ok:{nick}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"no:{nick}"
                )
            ]
        ]
    )

    await bot.send_message(
        ADMIN_ID,
        f"📥 НОВАЯ VK ЗАЯВКА\n\n"
        f"👤 Ник: {nick}\n"
        f"🎂 Возраст: {age}\n"
        f"📡 Узнал: {source}\n"
        f"🎯 Цель: {goal}",
        reply_markup=kb
    )

    return web.json_response({"ok": True})
# ---------------- RCON ----------------
def swl_add(nick: str):
    with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
        return mcr.command(f"swl add {nick}")
        result = mcr.command(f"swl list")

# ---------------- STATES ----------------
class Form(StatesGroup):
    nick = State()
    age = State()
    source = State()
    goal = State()


# ---------------- START ----------------
@dp.message(CommandStart())
async def start(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Подать заявку", callback_data="apply")]
    ])

    await msg.answer("Добро пожаловать!\nНажмите кнопку чтобы подать заявку.", reply_markup=kb)


# ---------------- APPLY ----------------
@dp.callback_query(F.data == "apply")
async def apply(call: CallbackQuery, state: FSMContext):
    await state.set_state(Form.nick)
    await call.message.answer("Введите ваш Minecraft ник:")
    await call.answer()


# ---------------- NICK ----------------
@dp.message(Form.nick)
async def nick(msg: Message, state: FSMContext):
    await state.update_data(nick=msg.text.strip())
    await state.set_state(Form.age)
    await msg.answer("Ваш возраст?")


# ---------------- AGE ----------------
@dp.message(Form.age)
async def age(msg: Message, state: FSMContext):
    await state.update_data(age=msg.text.strip())
    await state.set_state(Form.source)
    await msg.answer("Откуда вы узнали о сервере?")


# ---------------- SOURCE ----------------
@dp.message(Form.source)
async def source(msg: Message, state: FSMContext):
    await state.update_data(source=msg.text.strip())
    await state.set_state(Form.goal)
    await msg.answer("Цель на сервере?")


# ---------------- GOAL + SEND ----------------
@dp.message(Form.goal)
async def goal(msg: Message, state: FSMContext):
    data = await state.get_data()

    nick = data["nick"]
    age = data["age"]
    source = data["source"]
    goal_text = msg.text.strip()

    pending[nick] = {
        "user_id": msg.from_user.id,
        "age": age,
        "source": source,
        "goal": goal_text
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✔️ Одобрить", callback_data=f"ok:{nick}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"no:{nick}")
        ]
    ])

    await bot.send_message(
        ADMIN_ID,
        f"📥 НОВАЯ ЗАЯВКА\n\n"
        f"👤 Ник: {nick}\n"
        f"🎂 Возраст: {age}\n"
        f"📡 Узнал: {source}\n"
        f"🎯 Цель: {goal_text}",
        reply_markup=kb
    )

    await msg.answer("✅ Заявка отправлена администрации!")
    await state.clear()


# ---------------- ACCEPT ----------------
@dp.callback_query(F.data.startswith("ok:"))
async def accept(call: CallbackQuery):
    nick = call.data.split(":")[1]

    try:
        swl_add(nick)

        user_id = pending[nick]["user_id"]

        await bot.send_message(
            user_id,
            f"✅ Ваша заявка одобрена!\nВы добавлены в whitelist.\nНик: {nick}"
        )

        await call.message.edit_text(f"✔️ Одобрено\nИгрок: {nick}")

    except Exception as e:
        await call.message.answer(f"RCON ошибка: {e}")

    await call.answer()


# ---------------- DENY (запрос причины) ----------------
@dp.callback_query(F.data.startswith("no:"))
async def deny(call: CallbackQuery):
    nick = call.data.split(":")[1]

    deny_buffer["nick"] = nick

    await call.message.answer("Введите причину отказа:")
    await call.answer()


# ---------------- REASON FOR DENY ----------------
@dp.message()
async def deny_reason(msg: Message):
    if "nick" not in deny_buffer:
        return

    nick = deny_buffer["nick"]
    reason = msg.text

    user_id = pending.get(nick, {}).get("user_id")

    if user_id:
        await bot.send_message(
            user_id,
            f"❌ Ваша заявка отклонена\n\nПричина: {reason}"
        )

    await msg.answer(f"❌ Отклонено: {nick}\nПричина: {reason}")

    deny_buffer.clear()

async def start_api():

    app = web.Application()

    app.router.add_post(
        "/application",
        create_application
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        8080
    )

    await site.start()
# ---------------- RUN ----------------
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
