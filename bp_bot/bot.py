import asyncio
import io
import logging
import uuid
from decimal import Decimal
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
    BotCommand,
)
from pydantic import ValidationError
from .catalog import ProductChoice
from .domain import BusinessError, ProposalPatch, authorize
from .models import AppValue
from .documents import validate_letterhead

log = logging.getLogger(__name__)
HELP = """АТехника — коммерческие предложения
/new — новое КП, затем напишите запрос или отправьте голосовое
/catalog [поиск] — каталог с SKU
/my — доступные КП
/show НОМЕР [ВЕРСИЯ] — карточка
/edit НОМЕР ВЕРСИЯ текст — новая редакция
/history НОМЕР — история
/finish НОМЕР ВЕРСИЯ — завершить
/files НОМЕР ВЕРСИЯ — получить Word и PDF
/cancel — отменить ввод

Без AI можно заполнить так:
клиент=ООО Заря; позиции=SKU:1; поставка=10 рабочих дней; до=2026-12-01
Несколько позиций: позиции=SKU1:1,SKU2:2

Начальник:
/users — пользователи
/user ID manager|sales_head|chief ОТДЕЛ Имя Фамилия
/disable ID — отключить пользователя
/vat НОМЕР ВЕРСИЯ СТАВКА ПРИЧИНА — изменить НДС
Пришлите CSV с подписью /import для обновления каталога.
Пришлите чистый DOCX-бланк с подписью /letterhead.
"""


def buttons(qid, version):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Изменить", callback_data=f"edit:{qid}:{version}"),
                InlineKeyboardButton(text="Завершить", callback_data=f"finish:{qid}:{version}"),
            ],
            [
                InlineKeyboardButton(text="Word и PDF", callback_data=f"files:{qid}:{version}"),
                InlineKeyboardButton(text="История", callback_data=f"history:{qid}:{version}"),
            ],
        ]
    )


def format_view(v):
    p = v["payload"]
    lines = [
        f"КП-{v['id']:05d} • версия {v['version']} • "
        + ("Завершено" if v["status"] == "finished" else "Черновик"),
        f"Клиент: {p.get('client') or 'не указан'}",
        f"Менеджер: {p['manager']}",
    ]
    for i in p["items"]:
        lines.append(
            f"{i['sku']} · {i['name']} · {i['quantity']} шт. × {i['unit_price']} ₽ "
            f"= {i['line_total']} ₽; НДС {i['vat_rate']}% включён"
        )
    lines += [
        f"Итого: {p['totals']['gross']} ₽; в т. ч. НДС {p['totals']['vat']} ₽",
        "Оплата: 100% предоплата",
        f"Поставка: {p.get('delivery_terms') or 'не указана'}",
        p["collection"],
        f"Действует до: {p.get('valid_until') or 'не указано'}",
    ]
    if v["missing"]:
        lines.append("Нужно заполнить: " + "; ".join(v["missing"]))
    return "\n".join(lines)


class UI:
    def __init__(self, bot, quotes, ai, store, settings):
        self.bot, self.quotes, self.ai, self.store, self.settings = bot, quotes, ai, store, settings
        self.dp = Dispatcher()
        self.register()

    def state(self, uid, value=None, delete=False):
        with self.quotes.sessions.begin() as s:
            key = f"conversation:{uid}"
            row = s.get(AppValue, key)
            if delete:
                if row:
                    s.delete(row)
                return None
            if value is not None:
                if row:
                    row.value = value
                else:
                    s.add(AppValue(key=key, value=value))
                return value
            return row.value if row else None

    async def send(self, message, text, markup=None):
        for offset in range(0, len(text), 3500):
            await message.answer(
                text[offset : offset + 3500], reply_markup=markup if offset + 3500 >= len(text) else None
            )

    async def show(self, message, qid, version=None):
        v = await asyncio.to_thread(self.quotes.view, message.chat.id, qid, version)
        await self.send(message, format_view(v), buttons(v["id"], v["version"]))

    async def files(self, message, qid, version):
        uid = message.chat.id
        job = await asyncio.to_thread(self.quotes.request_files, uid, qid, version)
        if job["state"] != "done":
            await message.answer(
                "Документы в очереди. Через несколько секунд нажмите «Word и PDF» ещё раз.",
                reply_markup=buttons(qid, version),
            )
            return
        for extension in ("docx", "pdf"):
            # Re-check authorization immediately before retrieval/delivery.
            await asyncio.to_thread(self.quotes.view, uid, qid, version)
            raw = await asyncio.to_thread(self.store.get, job[extension + "_key"])
            await message.answer_document(
                BufferedInputFile(raw, filename=f"KP-{qid:05d}_v{version}.{extension}")
            )

    async def submit(self, message, text, key, state):
        patch = await self.ai.parse(text, self.quotes.today())
        if not patch.model_dump(exclude_none=True, exclude={"forbidden_requests"}):
            raise BusinessError(
                "Не найдены поля КП. Укажите клиента, SKU и количество, срок поставки и срок предложения."
            )
        await self.submit_patch(message, patch, key, state)

    async def submit_patch(self, message, patch, key, state):
        uid = message.chat.id
        for index, item in enumerate(patch.items or []):
            try:
                product = await asyncio.to_thread(self.quotes.resolve_product, uid, item.product_query)
                item.product_query = product.sku
            except ProductChoice as choice:
                token = uuid.uuid4().hex[:16]
                await asyncio.to_thread(
                    self.state,
                    uid,
                    {
                        "mode": "product",
                        "token": token,
                        "patch": patch.model_dump(mode="json"),
                        "index": index,
                        "options": [p.sku for p in choice.products],
                        "request_key": key,
                        "target": state,
                    },
                )
                lines = [f"Уточните комплектацию для «{choice.query}». Выберите позицию:"]
                keyboard = []
                for n, p in enumerate(choice.products):
                    lines.append(
                        f"{n + 1}. {p.name} — {p.configuration[:240]}\n{p.price} {p.currency}; {p.sku}"
                    )
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                text=f"{n + 1}. {p.name}"[:60], callback_data=f"product:{token}:{n}"
                            )
                        ]
                    )
                keyboard.append([InlineKeyboardButton(text="Отменить", callback_data="cancel")])
                await self.send(message, "\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
                return
        if state and state.get("mode") == "edit":
            result = await asyncio.to_thread(
                self.quotes.revise, uid, state["id"], state["version"], patch, key
            )
        else:
            result = await asyncio.to_thread(self.quotes.create, uid, patch, key)
        await asyncio.to_thread(self.state, uid, delete=True)
        await self.show(message, result["id"], result["version"])

    def register(self):
        @self.dp.message(Command("start", "help"))
        async def start(m: Message):
            if m.chat.type != "private":
                return
            try:
                await asyncio.to_thread(self.quotes.user, m.from_user.id)
                await m.answer(HELP)
            except BusinessError:
                await m.answer(
                    f"Доступ ещё не предоставлен. Передайте начальнику ваш Telegram ID: {m.from_user.id}"
                )

        @self.dp.message(F.chat.type == "private")
        async def handle(m: Message):
            try:
                uid = m.from_user.id
                user = await asyncio.to_thread(self.quotes.user, uid)
                if m.document:
                    caption = (m.caption or "").strip()
                    if caption not in {"/import", "/letterhead"}:
                        raise BusinessError(
                            "Ручной Word пока не импортируется. Для правок используйте /edit."
                        )
                    authorize(user, chief=True)
                    if (m.document.file_size or 0) > self.settings.max_file_bytes:
                        raise BusinessError("Файл слишком большой.")
                    raw = io.BytesIO()
                    await self.bot.download(m.document, destination=raw)
                    data = raw.getvalue()
                    if caption == "/import":
                        n = await asyncio.to_thread(self.quotes.import_catalog, uid, data)
                        await m.answer(f"Каталог обновлён: {n} позиций.")
                    else:
                        await asyncio.to_thread(validate_letterhead, data)
                        key = f"letterheads/{uuid.uuid4().hex}.docx"
                        await asyncio.to_thread(
                            self.store.put,
                            key,
                            data,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                        await asyncio.to_thread(self.quotes.set_letterhead, uid, key)
                        await m.answer(
                            "Бланк сохранён. Он будет использован для новых КП и новых версий без бланка."
                        )
                    return
                state = await asyncio.to_thread(self.state, uid)
                request_key = f"message:{uid}:{m.message_id}"
                if m.voice:
                    if (
                        m.voice.duration > self.settings.max_voice_seconds
                        or (m.voice.file_size or 0) > self.settings.max_file_bytes
                    ):
                        raise BusinessError("Голосовое должно быть не длиннее 3 минут и не больше 10 МБ.")
                    raw = io.BytesIO()
                    await self.bot.download(m.voice, destination=raw)
                    text = await self.ai.transcribe(raw.getvalue())
                    token = uuid.uuid4().hex[:16]
                    await asyncio.to_thread(
                        self.state,
                        uid,
                        {
                            "mode": "voice",
                            "text": text,
                            "target": state if state and state.get("mode") == "edit" else None,
                            "request_key": request_key,
                            "token": token,
                        },
                    )
                    await self.send(
                        m,
                        "Проверьте распознанный текст:\n" + text,
                        InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="Использовать текст", callback_data=f"voice:{token}"
                                    ),
                                    InlineKeyboardButton(text="Отмена", callback_data="cancel"),
                                ]
                            ]
                        ),
                    )
                    return
                text = (m.text or "").strip()
                if not text:
                    return
                parts = text.split()
                command = parts[0].split("@")[0].lower()
                if command == "/cancel":
                    await asyncio.to_thread(self.state, uid, delete=True)
                    await m.answer("Ввод отменён.")
                elif command == "/new":
                    await asyncio.to_thread(self.state, uid, {"mode": "new"})
                    if len(parts) > 1:
                        await self.submit(m, text.split(maxsplit=1)[1], request_key, None)
                    else:
                        await m.answer(
                            "Напишите клиента, технику с количеством и сроки либо отправьте голосовое.\n"
                            "Пример: клиент=ООО Заря; позиции=SKU:1; поставка=10 рабочих дней; до=2026-12-01"
                        )
                elif command == "/catalog":
                    rows = await asyncio.to_thread(self.quotes.catalog, uid, " ".join(parts[1:]))
                    await self.send(
                        m,
                        "\n\n".join(
                            f"{p.sku}: {p.name}\n{p.configuration}\n"
                            f"{p.price} {p.currency}, НДС {p.vat_rate}% включён; "
                            f"цена до {p.valid_until}"
                            for p in rows
                        )
                        or "Каталог пуст. Начальник должен загрузить CSV.",
                    )
                elif command == "/my":
                    rows = await asyncio.to_thread(self.quotes.list_quotes, uid)
                    await self.send(
                        m,
                        "\n".join(f"/show {q['id']} — версия {q['version']}" for q in rows) or "КП пока нет.",
                    )
                elif command == "/show":
                    await self.show(m, int(parts[1]), int(parts[2]) if len(parts) > 2 else None)
                elif command == "/edit":
                    qid, version = int(parts[1]), int(parts[2])
                    await asyncio.to_thread(self.quotes.view, uid, qid, version)
                    target = {"mode": "edit", "id": qid, "version": version}
                    if len(parts) > 3:
                        await self.submit(m, text.split(maxsplit=3)[3], request_key, target)
                    else:
                        await asyncio.to_thread(self.state, uid, target)
                        await m.answer(
                            "Напишите изменения. Для замены техники перечислите весь новый состав КП."
                        )
                elif command == "/history":
                    await self.history(m, int(parts[1]))
                elif command == "/finish":
                    await asyncio.to_thread(self.quotes.finish, uid, int(parts[1]), int(parts[2]))
                    await self.show(m, int(parts[1]), int(parts[2]))
                elif command == "/files":
                    await self.files(m, int(parts[1]), int(parts[2]))
                elif command == "/vat":
                    qid, ver, vat, reason = (
                        int(parts[1]),
                        int(parts[2]),
                        Decimal(parts[3].replace(",", ".")),
                        " ".join(parts[4:]),
                    )
                    result = await asyncio.to_thread(
                        self.quotes.revise,
                        uid,
                        qid,
                        ver,
                        ProposalPatch(),
                        request_key,
                        vat=vat,
                        reason=reason,
                    )
                    await self.show(m, result["id"], result["version"])
                elif command == "/user":
                    await asyncio.to_thread(
                        self.quotes.set_user, uid, int(parts[1]), parts[2], parts[3], " ".join(parts[4:])
                    )
                    await m.answer("Пользователь сохранён.")
                elif command == "/disable":
                    target = next(
                        (
                            u
                            for u in await asyncio.to_thread(self.quotes.users, uid)
                            if u.telegram_id == int(parts[1])
                        ),
                        None,
                    )
                    if not target:
                        raise BusinessError("Пользователь не найден.")
                    await asyncio.to_thread(
                        self.quotes.set_user,
                        uid,
                        target.telegram_id,
                        target.role,
                        target.department,
                        target.name,
                        False,
                    )
                    await m.answer("Доступ отключён.")
                elif command == "/users":
                    users = await asyncio.to_thread(self.quotes.users, uid)
                    await self.send(
                        m,
                        "\n".join(
                            f"{u.telegram_id} · {u.name} · {u.role} · {u.department} · "
                            f"{'активен' if u.active else 'отключён'}"
                            for u in users
                        ),
                    )
                elif command.startswith("/"):
                    await m.answer("Неизвестная команда. Откройте /help.")
                else:
                    if state and state.get("mode") == "product":
                        raise BusinessError("Выберите технику кнопкой или отмените ввод /cancel.")
                    if state and state.get("mode") == "voice":
                        raise BusinessError("Подтвердите голосовое кнопкой или отмените ввод /cancel.")
                    await self.submit(m, text, request_key, state)
            except BusinessError as e:
                await self.send(m, str(e))
            except (ValidationError, ValueError, IndexError, ArithmeticError):
                await m.answer("Не удалось прочитать поля или команду. Проверьте формат в /help.")
            except Exception as e:
                log.error("message_failure type=%s", type(e).__name__)
                await m.answer("Операция не завершена. Повторите запрос или обратитесь к начальнику.")

        @self.dp.callback_query()
        async def callback(c: CallbackQuery):
            if not isinstance(c.message, Message) or c.message.chat.type != "private":
                await c.answer()
                return
            await c.answer()
            try:
                uid = c.from_user.id
                await asyncio.to_thread(self.quotes.user, uid)
                data = (c.data or "").split(":")
                if data[0] == "cancel":
                    await asyncio.to_thread(self.state, uid, delete=True)
                    await c.message.answer("Ввод отменён.")
                elif data[0] == "product":
                    st = await asyncio.to_thread(self.state, uid)
                    if not st or st.get("mode") != "product" or st.get("token") != data[1]:
                        raise BusinessError("Этот выбор уже обработан или отменён.")
                    selection = int(data[2])
                    if not 0 <= selection < len(st["options"]):
                        raise BusinessError("Недопустимая позиция.")
                    patch = ProposalPatch.model_validate(st["patch"])
                    patch.items[st["index"]].product_query = st["options"][selection]
                    await self.submit_patch(c.message, patch, st["request_key"], st["target"])
                elif data[0] == "voice":
                    st = await asyncio.to_thread(self.state, uid)
                    if not st or st.get("mode") != "voice" or st.get("token") != data[1]:
                        raise BusinessError("Этот запрос уже обработан или отменён.")
                    await self.submit(c.message, st["text"], st["request_key"], st["target"])
                else:
                    qid, ver = int(data[1]), int(data[2])
                    await asyncio.to_thread(self.quotes.view, uid, qid, ver)
                    if data[0] == "edit":
                        await asyncio.to_thread(self.state, uid, {"mode": "edit", "id": qid, "version": ver})
                        await c.message.answer(
                            "Напишите изменения или отправьте голосовое. Состав позиций заменяется целиком."
                        )
                    elif data[0] == "finish":
                        await asyncio.to_thread(self.quotes.finish, uid, qid, ver)
                        await self.show(c.message, qid, ver)
                    elif data[0] == "files":
                        await self.files(c.message, qid, ver)
                    elif data[0] == "history":
                        await self.history(c.message, qid)
            except BusinessError as e:
                await self.send(c.message, str(e))
            except Exception as e:
                log.error("callback_failure type=%s", type(e).__name__)
                await c.message.answer("Не удалось выполнить действие. Обновите карточку КП.")

    async def history(self, message, qid):
        rows = await asyncio.to_thread(self.quotes.history, message.chat.id, qid)
        await self.send(
            message,
            "\n".join(
                f"Версия {r['version']} · {r['status']} · {r['created']}\n/show {qid} {r['version']}"
                for r in rows
            ),
        )

    async def run(self):
        webhook = await self.bot.get_webhook_info()
        if webhook.url:
            raise RuntimeError("Existing webhook detected; remove it explicitly before switching to polling")
        await self.bot.set_my_commands(
            [
                BotCommand(command=c, description=d)
                for c, d in [
                    ("new", "Новое КП"),
                    ("catalog", "Каталог"),
                    ("my", "Мои КП"),
                    ("cancel", "Отменить ввод"),
                    ("help", "Помощь"),
                ]
            ]
        )
        # Sequential processing prevents races between conversation context and message edits.
        # Rendering runs in a separate durable worker, so LibreOffice never blocks polling.
        await self.dp.start_polling(
            self.bot, handle_as_tasks=False, allowed_updates=["message", "callback_query"]
        )
