import os
import io
import re
import time
import uuid
import html
import shutil
import asyncio
from pathlib import Path
from aiogram import Router, F, types, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import logging
import json
from tg_bot.config import BASE_DIR, MATERIALS_DIR, RAZBOR_DIR, KARUSEL_DIR, VIDEOS_DIR
from tg_bot.engine.agent_runner import run_agent_task
from tg_bot.engine.file_extractor import extract_text_from_file
from tg_bot.engine.elevenlabs_scribe import async_transcribe_media, format_seconds
from tg_bot.engine.video_pipeline import async_edit_and_render_video
from tg_bot.engine.carousel_builder import (
    run_build_karusel,
    build_dynamic_carousel,
    remake_competitor_carousel,
    AVAILABLE_DECKS,
    generate_carousel_draft,
    render_carousel_from_text,
    update_draft_with_instructions,
    get_draft,
    save_draft
)
from tg_bot.engine.formatter import markdown_to_telegram_html
from tg_bot.engine.insta_monitor import is_instagram_url, extract_instagram_url, analyze_instagram_post
from tg_bot.engine.yandex_disk import is_yandex_disk_url, extract_yandex_disk_url, download_yandex_disk_file

logger = logging.getLogger(__name__)
router = Router()

ROLES_FILE = BASE_DIR / "tg_bot" / "topic_roles.json"

def load_topic_roles() -> dict[int, str]:
    if ROLES_FILE.exists():
        try:
            data = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
            return {int(k): v for k, v in data.items()}
        except Exception:
            pass
    return {}

def save_topic_role(thread_id: int, role: str):
    roles = load_topic_roles()
    roles[thread_id] = role
    try:
        ROLES_FILE.write_text(json.dumps({str(k): v for k, v in roles.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

FORUM_TOPICS = [
    {
        "name": "✍️ Копирайтер",
        "role": "copywriter",
        "welcome": "✍️ <b>Копирайтер команды Амалии</b>\n\nПишите задачи на посты в Telegram-канал, серии Stories, прогревы к вебинарам/Системе или хуки по ВИСП для Reels.\nЯ упакую смыслы живым языком Амалии с ее бытовыми образами и рублеными добивками."
    },
    {
        "name": "🎨 Дизайнер",
        "role": "designer",
        "welcome": "🎨 <b>Дизайнер и Арт-директор</b>\n\nНапишите <b>любую новую тему или тезисы карусели</b> — я сразу составлю структуру, сверстаю карточки 1080x1350 в фирменном стиле и пришлю готовые PNG в чат!\n\nИли выберите готовую тему: <code>" + ", ".join(AVAILABLE_DECKS[:8]) + "</code>."
    },
    {
        "name": "🔍 Главред",
        "role": "editor",
        "welcome": "🔍 <b>Главный редактор и Факт-чекер</b>\n\nПрисылайте готовые тексты на аудит. Я проверю соответствие первоисточникам (01 Материалы), вычищу стоп-слова («не потому что X, а Y», канцелярит, инфостиль), проверю тире «-» и правило «диагноз бесплатно, лечение в продукте»."
    },
    {
        "name": "🎙 Смысловик",
        "role": "analyst",
        "welcome": "🎙 <b>Смысловик и Аналитик созвонов</b>\n\nСкидывайте сюда аудиозаписи, голосовые, кружки или файлы транскриптов (.docx, .pdf, .txt, .html).\nЯ моментально вытащу: задачи по исполнителям, дословные цитаты Амалии и смысловые блоки для контента."
    },
    {
        "name": "⚙️ Техспециалист",
        "role": "tech",
        "welcome": "⚙️ <b>Технический специалист</b>\n\nОтвечаю за инфраструктуру: сервер, работу бота, Antigravity CLI (agy), лендинги, GetCourse и деплой.\nЗадавайте вопросы по технической части или отправляйте команды <code>/status</code>, <code>/deploy</code>."
    },
    {
        "name": "🎬 Видеомонтажер",
        "role": "video_editor",
        "welcome": "🎬 <b>Видеомонтажер и Reels-мейкер команды Амалии</b>\n\nСкидывайте сюда исходники видео, дубли, кружки или сценарии Reels.\nЯ построю монтажный план по методологии video-use: пословная транскрибация через ElevenLabs Scribe, вырезка пауз и слов-паразитов, динамичные субтитры (2-3 слова капсом), перебивки и хуки по ВИСП!"
    }
]

HELP_TEXT = """
👋 <b>Команда специалистов проекта Амалии Саргсян в сборе!</b>

👥 <b>Специалисты в команде:</b>
• ✍️ <b>Копирайтер</b> — посты в канал, сценарии Stories, хуки ВИСП и прогревы
• 🎨 <b>Дизайнер</b> — генерация каруселей 1080x1350 (PNG), визуал
• 🔍 <b>Главред</b> — факт-чекинг, вычитка стоп-слов, контроль голоса
• 🎙 <b>Смысловик</b> — расшифровка аудио/созвонов, извлечение задач и цитат
• ⚙️ <b>Техспециалист</b> — инфраструктура, сервер, бот, GetCourse
• 🎬 <b>Видеомонтажер</b> — разбор видео и дублей (ElevenLabs Scribe), вырезка пауз/паразитов, EDL, субтитры Reels

📌 <b>Как создать ветки в группе:</b>
1. Включите <b>«Темы» (Topics)</b> в настройках вашей группы Telegram.
2. Отправьте в группу команду <code>/setup_forum</code> — бот автоматически создаст все ветки специалистов с инструкциями!

📌 <b>Команды для любого чата:</b>
• <code>/setup_forum</code> — создание веток специалистов в группе
• <code>/post [тема]</code> — задача для Копирайтера
• <code>/karusel [тема]</code> — задача для Дизайнера (сборка PNG)
• <code>/check [текст]</code> — задача для Главреда (аудит)
• <code>/sozvon [файл/аудио]</code> — задача для Смысловика (разбор)
• <code>/video [видео/текст]</code> — задача для Видеомонтажера (разбор/EDL/субтитры)
• <code>/insta [ссылка на Reels]</code> — скачать, расшифровать и разобрать рилс
• <code>/status</code> — статус бота, материалов и системы
"""


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")

@router.message(Command("setup_forum"))
async def cmd_setup_forum(message: types.Message):
    if not message.chat.is_forum:
        await message.answer(
            "⚠️ <b>В группе пока не включены Темы (Topics)!</b>\n\n"
            "Чтобы я мог создать ветки специалистов:\n"
            "1. Зайдите в <b>Настройки группы</b> (в Telegram)\n"
            "2. Включите переключатель <b>«Темы» / «Topics»</b>\n"
            "3. Снова напишите команду <code>/setup_forum</code>",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer("🛠 Начинаю создание рабочих веток специалистов...", parse_mode="HTML")
    created_count = 0

    for topic_info in FORUM_TOPICS:
        try:
            topic = await message.bot.create_forum_topic(
                chat_id=message.chat.id,
                name=topic_info["name"]
            )
            save_topic_role(topic.message_thread_id, topic_info["role"])
            
            await message.bot.send_message(
                chat_id=message.chat.id,
                message_thread_id=topic.message_thread_id,
                text=topic_info["welcome"],
                parse_mode="HTML"
            )
            created_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            await message.answer(f"Не удалось создать тему {topic_info['name']}: {e}")

    await status_msg.edit_text(
        f"✅ <b>Форум готов! Создано {created_count} рабочих веток специалистов.</b>\n\n"
        "Теперь вы можете писать в нужную ветку — бот автоматически будет отвечать от имени соответствующего эксперта команды!",
        parse_mode="HTML"
    )

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    mat_count = len([f for f in MATERIALS_DIR.rglob("*.*") if not f.name.startswith(".")]) if MATERIALS_DIR.exists() else 0
    razbor_count = len(list(RAZBOR_DIR.glob("*.md"))) if RAZBOR_DIR.exists() else 0
    await message.answer(
        f"✅ <b>Команда активна и готова к работе!</b>\n\n"
        f"📁 Файлов в 01 Материалы: <code>{mat_count}</code> (транскрипты и выгрузки канала)\n"
        f"📝 Разборов в 02 Разборы созвонов: <code>{razbor_count}</code>\n"
        f"🧠 Мозг: Google Antigravity CLI (agy)",
        parse_mode="HTML"
    )


async def download_tg_file(bot: Bot, file_path: str | None, destination: Path | io.BytesIO) -> None:
    """
    Safely and fast downloads a file from Telegram.
    If local Bot API server has already saved it on disk, copies or reads it directly.
    """
    if not file_path:
        raise ValueError("file_path is empty")

    local_p = Path(file_path)
    if local_p.exists() and local_p.is_file():
        if isinstance(destination, Path):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_p, destination)
            return
        elif isinstance(destination, io.BytesIO):
            destination.write(local_p.read_bytes())
            destination.seek(0)
            return

    if isinstance(destination, Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
    await bot.download_file(file_path, destination=destination)


async def send_media_group_safe(message: types.Message, images: list[Path]):
    """Sends all images (even if > 10) in chunks of up to 10 photos or individual photos."""
    if not images:
        return
    
    # Разбиваем список изображений на чанки максимум по 10 штук (лимит Telegram API)
    chunks = [images[i:i+10] for i in range(0, len(images), 10)]
    
    for chunk in chunks:
        if len(chunk) == 1:
            img_path = chunk[0]
            try:
                if message.message_thread_id:
                    await message.bot.send_photo(
                        chat_id=message.chat.id,
                        message_thread_id=message.message_thread_id,
                        photo=FSInputFile(str(img_path)),
                        request_timeout=60.0
                    )
                else:
                    await message.bot.send_photo(
                        chat_id=message.chat.id,
                        photo=FSInputFile(str(img_path)),
                        request_timeout=60.0
                    )
            except Exception as single_err:
                logger.error(f"Error sending single photo {img_path}: {single_err}")
            await asyncio.sleep(0.3)
        else:
            media_group = [InputMediaPhoto(media=FSInputFile(str(img_path))) for img_path in chunk]
            try:
                if message.message_thread_id:
                    await message.bot.send_media_group(
                        chat_id=message.chat.id,
                        message_thread_id=message.message_thread_id,
                        media=media_group,
                        request_timeout=180.0
                    )
                else:
                    await message.bot.send_media_group(
                        chat_id=message.chat.id,
                        media=media_group,
                        request_timeout=180.0
                    )
            except Exception as e:
                logger.error(f"Error sending media group: {e}, falling back to single photos...")
                for img_path in chunk:
                    try:
                        if message.message_thread_id:
                            await message.bot.send_photo(
                                chat_id=message.chat.id,
                                message_thread_id=message.message_thread_id,
                                photo=FSInputFile(str(img_path)),
                                request_timeout=60.0
                            )
                        else:
                            await message.bot.send_photo(
                                chat_id=message.chat.id,
                                photo=FSInputFile(str(img_path)),
                                request_timeout=60.0
                            )
                    except Exception as single_err:
                        logger.error(f"Error sending photo {img_path}: {single_err}")
            await asyncio.sleep(0.3)

USER_EDIT_STATES: dict[int, str] = {}
USER_EDIT_PROMPT_MSGS: dict[int, types.Message] = {}
USER_PHOTO_WAIT_STATES: dict[int, str] = {}
USER_PHOTO_PROMPT_MSGS: dict[int, types.Message] = {}
USER_PHOTO_CHOICE_MSGS: dict[int, types.Message] = {}

def get_carousel_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Отрисовать карточки 1080x1350", callback_data=f"render:{draft_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать текст / СТА", callback_data=f"edit_draft:{draft_id}")]
    ])

async def handle_carousel_generation(message: types.Message, query: str):
    """Handles template rendering, direct PNG rendering for ready verified texts, or drafting for new topics."""
    clean_query = query.strip()
    
    matched_template = None
    for deck in AVAILABLE_DECKS:
        if clean_query.lower() == deck:
            matched_template = deck
            break
            
    if matched_template or (clean_query in AVAILABLE_DECKS):
        target = matched_template or "voda"
        status_msg = await message.answer(f"🎨 Собираю шаблонную карусель <b>{target}</b>...", parse_mode="HTML")
        success, log, images, target_deck = run_build_karusel(target)
        try:
            await status_msg.delete()
        except Exception:
            pass
            
        if images:
            await send_media_group_safe(message, images)
        return

    is_ready_text = any(k in clean_query.lower() for k in ["слайд 1", "слайд 2", "обложка:", "1 слайд", "1.", "2.", "3.", "слайд 3", "слайд 4"]) and len(clean_query.split("\n")) >= 3

    # Если передан готовый проверенный текст — сохраняем черновик и даем выбор фото
    if is_ready_text:
        draft_id = save_draft(topic="Пользовательская карусель", text=clean_query)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Оставить стандартное фото", callback_data=f"render_run:{draft_id}:default")],
            [InlineKeyboardButton(text="📸 Загрузить новое фото для карусели", callback_data=f"render_photo_wait:{draft_id}")]
        ])
        await message.answer(
            "✅ <b>Готовый текст карусели принят без изменений!</b>\n\n"
            "<i>Выберите фотографию для финального слайда:</i>",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    # Если передана только тема — генерируем черновик через копирайтера
    status_msg = await message.answer("🔄 <b>Запуск генерации текста карусели:</b> Копирайтер...", parse_mode="HTML")
    
    async def update_status(text: str):
        try:
            await status_msg.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

    clean_post_text, draft_id, model_name = await generate_carousel_draft(
        topic=clean_query,
        status_callback=update_status
    )
    
    try:
        await status_msg.delete()
    except Exception:
        pass
        
    formatted_html = markdown_to_telegram_html(clean_post_text)
    await message.answer(
        f"✅ <b>Текст карусели сгенерирован:</b>\n\n{formatted_html}\n\n<i>👇 Нажмите «Отрисовать», чтобы собрать карточки 1080x1350, либо «Редактировать»:</i>",
        parse_mode="HTML",
        reply_markup=get_carousel_keyboard(draft_id)
    )

@router.callback_query(F.data.startswith("edit_draft:"))
async def on_edit_draft_prompt(callback: CallbackQuery):
    draft_id = callback.data.split("edit_draft:")[-1]
    draft = get_draft(draft_id)
    if not draft:
        await callback.answer("⚠️ Черновик не найден или устарел.", show_alert=True)
        return

    USER_EDIT_STATES[callback.from_user.id] = draft_id
    await callback.answer("✏️ Режим редактирования текста включен!")
    edit_msg = await callback.message.reply(
        "✏️ <b>Напишите ваши правки к тексту карусели:</b>\n\n"
        "Отправьте сообщением в чат:\n"
        "• Либо инструкцию: например <i>«Замени СТА на кодовое слово СИСТЕМА и позови на бесплатный аудит»</i> или <i>«Сделай Слайд 3 короче»</i>\n"
        "• Либо скопируйте текст выше, отредактируйте и пришлите обновленный вариант целиком.\n\n"
        "<i>Главред обновит черновик и выдаст готовый вариант с кнопкой отрисовки.</i>",
        parse_mode="HTML"
    )
    USER_EDIT_PROMPT_MSGS[callback.from_user.id] = edit_msg

@router.callback_query(F.data.startswith("render:"))
async def on_render_carousel(callback: CallbackQuery):
    draft_id = callback.data.split("render:")[-1]
    draft = get_draft(draft_id)
    if not draft:
        await callback.answer("⚠️ Черновик не найден или устарел.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ Оставить стандартное фото", callback_data=f"render_run:{draft_id}:default")],
        [InlineKeyboardButton(text="📸 Загрузить новое фото для карусели", callback_data=f"render_photo_wait:{draft_id}")]
    ])
    await callback.answer()
    choice_msg = await callback.message.reply(
        "📸 <b>Выбор фотографии Амалии для финального слайда:</b>\n\n"
        "• <b>Оставить стандартное:</b> Дизайнер возьмет основное фото Амалии из пула.\n"
        "• <b>Загрузить новое:</b> вы сможете скинуть свежее фото (файлом или картинкой), и бот поставит именно его.",
        parse_mode="HTML",
        reply_markup=kb
    )
    USER_PHOTO_CHOICE_MSGS[callback.from_user.id] = choice_msg

@router.callback_query(F.data.startswith("render_run:"))
async def on_render_run(callback: CallbackQuery):
    parts = callback.data.split(":")
    draft_id = parts[1]
    draft = get_draft(draft_id)
    if not draft:
        await callback.answer("⚠️ Черновик не найден или устарел.", show_alert=True)
        return

    # Удаляем сообщение с кнопками выбора фото
    choice_msg = USER_PHOTO_CHOICE_MSGS.pop(callback.from_user.id, None)
    if choice_msg:
        try:
            await choice_msg.delete()
        except Exception:
            pass

    await callback.answer("🎨 Дизайнер приступил к сборке карточек!")
    status_msg = await callback.message.answer("🎨 <b>[Дизайнер]</b> Верстает карточки 1080x1350 в фирменном стиле...", parse_mode="HTML")
    
    async def update_status(text: str):
        try:
            await status_msg.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

    success, log, images, deck_name, model_name = await render_carousel_from_text(
        text=draft["text"],
        topic=draft.get("topic", "Карусель"),
        status_callback=update_status,
        custom_photo_path=None
    )
    
    try:
        await status_msg.delete()
    except Exception:
        pass

    if not images:
        escaped_log = html.escape(log[:1000])
        await callback.message.answer(
            f"⚠️ Не удалось собрать карточки:\n<pre><code>{escaped_log}</code></pre>",
            parse_mode="HTML"
        )
        return

    await send_media_group_safe(callback.message, images)
    kb_change = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Заменить фото на финальном слайде", callback_data=f"render_photo_wait:{draft_id}")]
    ])
    await callback.message.answer(
        "✅ <b>Карточки 1080x1350 готовы!</b>\n"
        "<i>Если хотите поставить другое фото — нажмите кнопку ниже:</i>",
        parse_mode="HTML",
        reply_markup=kb_change
    )

@router.callback_query(F.data.startswith("render_photo_wait:"))
async def on_render_photo_wait(callback: CallbackQuery):
    draft_id = callback.data.split("render_photo_wait:")[-1]
    draft = get_draft(draft_id)
    if not draft:
        await callback.answer("⚠️ Черновик не найден или устарел.", show_alert=True)
        return

    # Удаляем сообщение с кнопками выбора фото
    choice_msg = USER_PHOTO_CHOICE_MSGS.pop(callback.from_user.id, None)
    if choice_msg:
        try:
            await choice_msg.delete()
        except Exception:
            pass

    USER_PHOTO_WAIT_STATES[callback.from_user.id] = draft_id
    await callback.answer("📸 Ожидаю фото...")
    p_msg = await callback.message.reply(
        "📸 <b>Отправьте фотографию Амалии прямо в чат</b> (картинкой или файлом без сжатия).\n\n"
        "<i>Дизайнер сразу подставит её в финальный CTA-слайд и сгенерирует готовую карусель 1080x1350.</i>",
        parse_mode="HTML"
    )
    USER_PHOTO_PROMPT_MSGS[callback.from_user.id] = p_msg

@router.message(Command("karusel"))
async def cmd_karusel(message: types.Message):
    args = message.text.replace("/karusel", "").strip()
    await handle_carousel_generation(message, args)

@router.message(Command("photo"))
async def cmd_upload_photo(message: types.Message):
    await message.answer(
        "📸 <b>Загрузка фото Амалии для каруселей:</b>\n\n"
        "Отправьте фотографию в чат с подписью <code>/photo</code> или словом <b>«фото»</b> — бот автоматически сохранит её в пул фотографий для финальных слайдов каруселей!",
        parse_mode="HTML"
    )

def determine_role(message: types.Message) -> tuple[str, str]:
    text = (message.text or message.caption or "").strip()
    thread_id = message.message_thread_id

    import re
    if text.startswith("/post") or text.startswith("/hooks") or text.startswith("/story"):
        return "copywriter", text.replace("/post", "").replace("/hooks", "").replace("/story", "").strip() or "Напиши пост в Telegram-канал голосом Амалии."
    elif text.startswith("/karusel"):
        return "designer", text.replace("/karusel", "").strip() or "Собери карусель."
    elif text.startswith("/check"):
        return "editor", text.replace("/check", "").strip() or "Проверь текст на факт-чек и голос."
    elif text.startswith("/sozvon"):
        return "analyst", text.replace("/sozvon", "").strip() or "Сделай разбор созвона по методологии проекта."
    elif text.startswith("/video") or text.startswith("/reels") or text.startswith("/cut") or text.startswith("/montage"):
        clean_v = re.sub(r'^(?:/video|/reels|/cut|/montage)\s*', '', text, flags=re.IGNORECASE).strip()
        return "video_editor", clean_v or "Сделай монтажный разбор видео/сценария по методологии video-use."
    elif text.startswith("/tech") or text.lower().startswith("тех:") or text.lower().startswith("техспец:") or text.lower().startswith("техник:"):
        clean_t = re.sub(r'^(?:/tech|тех:|техспец:|техник:)\s*', '', text, flags=re.IGNORECASE).strip()
        return "tech", clean_t or "Покажи статус инфраструктуры."

    # Persistent topic mapping
    topic_roles = load_topic_roles()
    if thread_id and thread_id in topic_roles:
        return topic_roles[thread_id], text

    # Smart heuristics
    lower_text = text.lower()
    if any(k in lower_text for k in ["обложка:", "слайд 1", "слайд 2", "послайдовый сценарий", "карусель для", "карточки карусели"]):
        return "designer", text

    video_keywords = [
        "монтаж", "видеомонтаж", "смонтируй", "нарезка", "edl", "видео-дубли",
        "субтитры для видео", "video-use", "исходник видео", "хронометраж", "склейка"
    ]
    if any(k in lower_text for k in video_keywords) and not any(w in lower_text for w in ["карусель", "пост в канал"]):
        return "video_editor", text

    tech_keywords = [
        "сервер", "деплой", "deploy", "systemd", "getcourse", "вебхук", "бот упал",
        "перезапусти", "рестарт", "restart", "ошибка в коде", "traceback", "баг", "скрипт",
        "python", "питон", "прокси", "proxy", "память", "диск", "токен", "api key",
        "bash", "конфиг", "build_karusel", "pillow", "шрифт", "cli", "agy"
    ]
    if any(k in lower_text for k in tech_keywords) and not any(w in lower_text for w in ["пост", "рилс", "reels", "сторис", "прогрев"]):
        return "tech", text

    return "copywriter", text

async def send_formatted_response(message: types.Message, wait_msg: types.Message | None, raw_response: str, model_name: str = ""):
    full_text = raw_response
    if model_name:
        full_text += f"\n\n---\n🧠 <i>Модель: {model_name}</i>"

    formatted_html = markdown_to_telegram_html(full_text)
    
    if len(formatted_html) > 4000:
        chunks = [formatted_html[i:i+3900] for i in range(0, len(formatted_html), 3900)]
    else:
        chunks = [formatted_html]

    try:
        if wait_msg:
            await wait_msg.edit_text(chunks[0], parse_mode="HTML")
        else:
            await message.answer(chunks[0], parse_mode="HTML")
            
        for chunk in chunks[1:]:
            await message.answer(chunk, parse_mode="HTML")
    except Exception:
        raw_chunks = [full_text[i:i+3900] for i in range(0, len(full_text), 3900)]
        if wait_msg:
            await wait_msg.edit_text(raw_chunks[0])
        else:
            await message.answer(raw_chunks[0])
        for chunk in raw_chunks[1:]:
            await message.answer(chunk)

@router.message(Command("insta"))
async def cmd_insta(message: types.Message):
    args = message.text.replace("/insta", "").strip()
    if not args:
        await message.answer(
            "🎬 <b>Отправьте ссылку на Instagram Reels или пост/карусель</b>\n\n"
            "Пример: <code>/insta https://www.instagram.com/p/C_...</code>\n"
            "• Для Reels: я скачаю видео, расшифрую речь Амалии и подготовлю пост для Telegram.\n"
            "• Для карусели: я скачаю карточки, перепишу голосом Амалии и сверстаю готовый альбом PNG!",
            parse_mode="HTML"
        )
        return
        
    wait_msg = await message.answer("📥 <b>Загружаю и анализирую публикацию из Instagram...</b>", parse_mode="HTML")
    response, model_name, images = await analyze_instagram_post(args)
    await send_formatted_response(message, wait_msg, response, model_name=model_name)
    if images:
        await send_media_group_safe(message, images)

@router.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/setup_forum") or message.text.startswith("/start") or message.text.startswith("/help") or message.text.startswith("/status") or message.text.startswith("/karusel") or message.text.startswith("/insta") or message.text.startswith("/adapt") or message.text.startswith("/remake"):
        return

    # Check if user sent an Instagram link directly
    if is_instagram_url(message.text):
        insta_url = extract_instagram_url(message.text)
        if insta_url:
            wait_msg = await message.answer("📥 <b>Загружаю и анализирую публикацию из Instagram...</b>", parse_mode="HTML")
            response, model_name, images = await analyze_instagram_post(insta_url)
            await send_formatted_response(message, wait_msg, response, model_name=model_name)
            if images:
                await send_media_group_safe(message, images)
            return

    # Check if user sent a Yandex Disk link directly
    if is_yandex_disk_url(message.text):
        yd_url = extract_yandex_disk_url(message.text)
        if yd_url:
            wait_msg = await message.answer("📥 <b>Скачиваю файл с Яндекс.Диска на сервер...</b>", parse_mode="HTML")
            role, prompt = determine_role(message)
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            success, dl_path, err = await download_yandex_disk_file(yd_url, VIDEOS_DIR)
            if not success or not dl_path or not dl_path.exists():
                await wait_msg.edit_text(f"⚠️ Не удалось скачать файл с Яндекс.Диска:\n{err}")
                return

            is_vid = dl_path.suffix.lower() in [".mov", ".mp4", ".avi", ".mkv", ".webm", ".m4v"]
            if is_vid or role == "video_editor":
                await wait_msg.edit_text(f"🎬 <b>Видео «{dl_path.name}» скачано!</b>\nЗапускаю пословную транскрибацию через ElevenLabs Scribe...", parse_mode="HTML")
                try:
                    scribe_data, packed_transcript, cuts = await async_transcribe_media(dl_path)
                    user_caption = prompt or "Сделай полный монтажный разбор этого видео по методологии video-use. Выдели лучшие дубли, отметь паузы и слова-паразиты, дай пословный таймлайн субтитров и хук по ВИСП."
                    cuts_summary = f"\n\n[ОБНАРУЖЕНО ПАУЗ И ПАРАЗИТОВ: {len(cuts)}]:\n" + "\n".join(
                        f"- {c['description']} [{format_seconds(c['start'])} -> {format_seconds(c['end'])}]"
                        for c in cuts[:15]
                    )
                    analysis_input = f"{user_caption}\n\n[ПОСЛОВНЫЙ ТРАНСКРИПТ SCRIBE]:\n{packed_transcript}{cuts_summary}"
                    response, model_name = await run_agent_task(role="video_editor", user_prompt=analysis_input)
                    await send_formatted_response(message, wait_msg, response, model_name=model_name)
                except Exception as e:
                    logger.error(f"Error processing Yandex Disk video: {e}", exc_info=True)
                    await wait_msg.edit_text(f"⚠️ Ошибка обработки видео: {e}")
                finally:
                    if dl_path.exists():
                        try:
                            dl_path.unlink()
                        except Exception:
                            pass
                return
            else:
                extracted_text = extract_text_from_file(dl_path)
                response, model_name = await run_agent_task(role=role, user_prompt=prompt or f"Разбери документ {dl_path.name}", attachment_text=extracted_text[:100000])
                await send_formatted_response(message, wait_msg, response, model_name=model_name)
                return

    # Check if user has active draft edit state
    if message.from_user and message.from_user.id in USER_EDIT_STATES:
        draft_id = USER_EDIT_STATES.pop(message.from_user.id)
        edit_prompt_msg = USER_EDIT_PROMPT_MSGS.pop(message.from_user.id, None)
        if edit_prompt_msg:
            try:
                await edit_prompt_msg.delete()
            except Exception:
                pass

        status_msg = await message.answer("✏️ <b>Главред вносит правки в черновик...</b>", parse_mode="HTML")
        
        async def update_status(text: str):
            try:
                await status_msg.edit_text(text, parse_mode="HTML")
            except Exception:
                pass

        updated_text, _ = await update_draft_with_instructions(
            draft_id=draft_id,
            instructions=message.text.strip(),
            status_callback=update_status
        )
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        if updated_text:
            formatted_html = markdown_to_telegram_html(updated_text)
            await message.answer(
                f"✅ <b>Текст карусели обновлен и проверен Главредом!</b>\n\n{formatted_html}\n\n<i>👇 Нажмите кнопку, чтобы отрисовать карточки, либо продолжите правки:</i>",
                parse_mode="HTML",
                reply_markup=get_carousel_keyboard(draft_id)
            )
            return

    role, prompt = determine_role(message)
    user_info = f"{message.from_user.id} (@{message.from_user.username or 'none'})" if message.from_user else "unknown"
    logger.info(f"📨 Сообщение от {user_info} | Ветка: {message.message_thread_id} | Роль: {role} | Текст: {prompt[:80]}")

    # In designer topic, trigger carousel generation
    if role in ("designer", "karusel"):
        await handle_carousel_generation(message, prompt)
        return

    role_titles = {
        "copywriter": "✍️ Копирайтер",
        "designer": "🎨 Дизайнер",
        "editor": "🔍 Главред",
        "analyst": "🎙 Смысловик",
        "tech": "⚙️ Техспециалист",
        "video_editor": "🎬 Видеомонтажер"
    }
    display_title = role_titles.get(role, role)

    wait_msg = await message.answer(
        f"⏳ {display_title} готовит ответ...",
        parse_mode="HTML"
    )
    
    response, model_name = await run_agent_task(role=role, user_prompt=prompt)
    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    file_name = doc.file_name or "document"
    caption = message.caption or ""

    # 1. Custom photo upload as file for pending carousel draft
    if message.from_user and message.from_user.id in USER_PHOTO_WAIT_STATES:
        draft_id = USER_PHOTO_WAIT_STATES.pop(message.from_user.id)
        p_msg = USER_PHOTO_PROMPT_MSGS.pop(message.from_user.id, None)
        if p_msg:
            try:
                await p_msg.delete()
            except Exception:
                pass

        draft = get_draft(draft_id)
        if draft:
            file_info = await message.bot.get_file(doc.file_id)
            img_bytes_io = io.BytesIO()
            await download_tg_file(message.bot, file_info.file_path, destination=img_bytes_io)
            image_bytes = img_bytes_io.getvalue()
            
            photos_dir = KARUSEL_DIR / "photos"
            photos_dir.mkdir(parents=True, exist_ok=True)
            custom_photo_path = photos_dir / f"custom_{draft_id}.jpg"
            custom_photo_path.write_bytes(image_bytes)

            status_msg = await message.answer("🎨 <b>[Дизайнер]</b> Вставляет фото и верстает карточки 1080x1350...", parse_mode="HTML")
            
            async def update_status(text: str):
                try:
                    await status_msg.edit_text(text, parse_mode="HTML")
                except Exception:
                    pass

            success, log, images, deck_name, model_name = await render_carousel_from_text(
                text=draft["text"],
                topic=draft.get("topic", "Карусель"),
                status_callback=update_status,
                custom_photo_path=custom_photo_path
            )
            
            try:
                await status_msg.delete()
            except Exception:
                pass

            if images:
                await send_media_group_safe(message, images)
                return

    # 2. Check for video sent as document or file size limit
    is_video_doc = any(file_name.lower().endswith(ext) for ext in [".mov", ".mp4", ".avi", ".mkv", ".webm", ".m4v"])
    file_size = getattr(doc, "file_size", 0) or 0
    max_tg_size = 2000 * 1024 * 1024  # 2 GB limit for local Telegram Bot API

    if file_size > max_tg_size:
        size_mb = file_size / (1024 * 1024)
        await message.reply(
            f"⚠️ <b>Файл «{file_name}» ({size_mb:.1f} МБ) превышает максимальный лимит Telegram (2 ГБ).</b>\n\n"
            f"Пожалуйста, загрузите его на Яндекс.Диск и отправьте ссылку.",
            parse_mode="HTML"
        )
        return

    if is_video_doc:
        size_mb = file_size / (1024 * 1024) if file_size else 0
        size_str = f" ({size_mb:.1f} МБ)" if size_mb > 0 else ""
        progress = VideoProgressBar(message)
        try:
            await progress.start(initial_text=f"📥 Скачивание <code>{file_name}</code>{size_str}...")
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            clean_name = re.sub(r"[^\w\.-]", "_", file_name)
            temp_video_path = VIDEOS_DIR / f"temp_{doc.file_unique_id}_{uuid.uuid4().hex[:4]}_{clean_name}"
            await progress.update(10, f"📥 Скачивание <code>{file_name}</code>{size_str}...", force=True)
            file_info = await message.bot.get_file(doc.file_id)
            await download_tg_file(message.bot, file_info.file_path, destination=temp_video_path)
            await process_and_render_video(
                message=message,
                video_path=temp_video_path,
                progress=progress,
                caption=caption,
                target_role="video_editor"
            )
        except Exception as e:
            logger.error(f"Error downloading video document {file_name}: {e}", exc_info=True)
            if progress.msg_handle:
                try:
                    await progress.msg_handle.edit_text(f"⚠️ Ошибка обработки видео: {e}")
                except Exception:
                    pass
        finally:
            progress.stop_ticker()
        return

    wait_msg = await message.answer(
        f"📥 Скачиваю и передаю в анализ <code>{file_name}</code>...",
        parse_mode="HTML"
    )

    save_path = MATERIALS_DIR / file_name
    try:
        file_info = await message.bot.get_file(doc.file_id)
        await download_tg_file(message.bot, file_info.file_path, destination=save_path)
    except Exception as dl_err:
        logger.error(f"Error downloading document {file_name}: {dl_err}")
        await wait_msg.edit_text(
            f"⚠️ <b>Не удалось скачать {file_name}:</b>\n{dl_err}",
            parse_mode="HTML"
        )
        return

    extracted_text = extract_text_from_file(save_path)

    role, prompt = determine_role(message)
    if not caption:
        if "созвон" in file_name.lower() or "транскрипт" in file_name.lower():
            role = "analyst"
            prompt = f"Разбери транскрипт созвона {file_name} и выдели главные смыслы, задачи и цитаты Амалии."
        else:
            prompt = f"Разбери документ {file_name}."

    response, model_name = await run_agent_task(
        role=role,
        user_prompt=prompt,
        attachment_text=extracted_text[:100000]
    )

    if role == "analyst":
        razbor_file = RAZBOR_DIR / f"Разбор_{Path(file_name).stem}.md"
        try:
            razbor_file.write_text(response, encoding="utf-8")
        except Exception:
            pass

    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.message(F.voice | F.audio)
async def handle_audio(message: types.Message):
    audio_obj = message.voice or message.audio
    wait_msg = await message.answer("🎙 <b>Смысловик</b> слушает и расшифровывает запись...", parse_mode="HTML")

    file_info = await message.bot.get_file(audio_obj.file_id)
    audio_bytes_io = io.BytesIO()
    await download_tg_file(message.bot, file_info.file_path, destination=audio_bytes_io)
    audio_bytes = audio_bytes_io.getvalue()

    mime_type = getattr(audio_obj, "mime_type", "audio/ogg") or "audio/ogg"
    caption = message.caption or "Расшифруй аудио, сделай разбор созвона/голосового: выдели задачи, смыслы для контента и цитаты Амалии."

    response, model_name = await run_agent_task(
        role="analyst",
        user_prompt=caption,
        audio_bytes=audio_bytes,
        mime_type=mime_type
    )

    await send_formatted_response(message, wait_msg, response, model_name=model_name)

class VideoProgressBar:
    """
    Live Telegram progress bar with real-time percentage and progress blocks.
    Respects Telegram's API rate-limiting with asynchronous throttling and a heartbeat ticker.
    """
    def __init__(self, message: types.Message, title: str = "Монтаж Reels"):
        self.message = message
        self.title = title
        self.msg_handle: types.Message | None = None
        self.start_time = time.time()
        self.last_update_time = 0.0
        self.current_percent = 5
        self.current_stage = "Инициализация видео-конвейера..."
        self._ticker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def _render_bar(self, percent: int, length: int = 10) -> str:
        percent = max(0, min(100, percent))
        filled = int(round(length * percent / 100))
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}] <b>{percent}%</b>"

    def _format_text(self, percent: int, stage_text: str) -> str:
        elapsed = int(time.time() - self.start_time)
        bar = self._render_bar(percent)
        return (
            f"🎬 <b>{self.title}:</b> {bar}\n\n"
            f"⏳ <b>Этап:</b> {stage_text}\n"
            f"⏱ <i>В работе: {elapsed}с</i>"
        )

    async def start(self, initial_msg: types.Message | None = None, initial_text: str | None = None):
        self.start_time = time.time()
        if initial_text:
            self.current_stage = initial_text
        text = self._format_text(self.current_percent, self.current_stage)
        if initial_msg:
            self.msg_handle = initial_msg
            try:
                await self.msg_handle.edit_text(text, parse_mode="HTML")
            except Exception:
                pass
        else:
            try:
                thread_id = self.message.message_thread_id
                self.msg_handle = await self.message.bot.send_message(
                    chat_id=self.message.chat.id,
                    message_thread_id=thread_id,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        self.last_update_time = time.time()
        self._start_ticker()

    def _start_ticker(self):
        if self._ticker_task and not self._ticker_task.done():
            self._ticker_task.cancel()

        async def ticker():
            while True:
                try:
                    await asyncio.sleep(2.5)
                    if time.time() - self.last_update_time >= 2.0:
                        await self._push_edit(self.current_percent, self.current_stage)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        self._ticker_task = asyncio.create_task(ticker())

    async def update(self, percent: int, stage_text: str, force: bool = False):
        async with self._lock:
            self.current_percent = max(self.current_percent, percent)
            self.current_stage = stage_text
            now = time.time()
            if not force and (now - self.last_update_time < 1.6):
                return
            await self._push_edit(self.current_percent, self.current_stage)

    async def _push_edit(self, percent: int, stage_text: str):
        if not self.msg_handle:
            return
        text = self._format_text(percent, stage_text)
        try:
            await self.msg_handle.edit_text(text, parse_mode="HTML")
            self.last_update_time = time.time()
        except Exception:
            pass

    async def finish(self, final_text: str = "✅ <b>Монтаж и субтитры готовы! Видео отправлено выше.</b>"):
        self.stop_ticker()
        elapsed = int(time.time() - self.start_time)
        bar = self._render_bar(100)
        text = (
            f"🎬 <b>{self.title}:</b> {bar}\n\n"
            f"{final_text}\n"
            f"⏱ <i>Общее время: {elapsed}с</i>"
        )
        if self.msg_handle:
            try:
                await self.msg_handle.edit_text(text, parse_mode="HTML")
            except Exception:
                pass

    def stop_ticker(self):
        if self._ticker_task and not self._ticker_task.done():
            self._ticker_task.cancel()


async def process_and_render_video(
    message: types.Message,
    video_path: Path,
    progress: VideoProgressBar,
    caption: str = "",
    target_role: str = "video_editor"
) -> None:
    """Runs full video-use pipeline: Scribe -> EDL -> 30ms afade -> Subtitles -> Loudnorm -> Telegram send."""
    job_id = uuid.uuid4().hex[:6]
    edit_dir = VIDEOS_DIR / f"edit_{video_path.stem}_{job_id}"
    try:
        await progress.update(
            20,
            "🎙 Извлекаю аудио и транскрибирую через ElevenLabs Scribe (пословные таймкоды)...",
            force=True
        )

        scribe_data, packed_transcript, cuts = await async_transcribe_media(video_path)

        await progress.update(
            42,
            f"✂️ Найдено {len(cuts)} пауз и заминок. Вырезаю лишнее и создаю 30ms склейки...",
            force=True
        )

        async def pipeline_cb(pct: int, text: str):
            await progress.update(pct, text)

        final_mov, srt_path, stats = await async_edit_and_render_video(
            video_path=video_path,
            scribe_data=scribe_data,
            output_dir=edit_dir,
            progress_callback=pipeline_cb
        )

        clean_caption = (caption or "").strip()
        user_wants_analysis = bool(clean_caption and not clean_caption.startswith("/"))

        response = None
        model_name = None
        if user_wants_analysis:
            await progress.update(
                92,
                "🧠 Формирую ответ по вашему запросу...",
                force=True
            )
            analysis_input = f"{clean_caption}\n\n[ПОСЛОВНЫЙ ТРАНСКРИПТ SCRIBE]:\n{packed_transcript}"
            response, model_name = await run_agent_task(
                role=target_role,
                user_prompt=analysis_input
            )

        orig_fmt = format_seconds(stats["original_duration"])
        cut_fmt = format_seconds(stats["cut_duration"])
        saved_str = f"{stats['saved_seconds']:.1f}с"

        from tg_bot.engine.broll_manager import list_broll_videos
        broll_count = len(list_broll_videos())
        broll_status = f"✅ вшиты ({broll_count} в банке)" if broll_count > 0 else "💡 подключите Google Drive через /broll"

        video_caption = (
            f"🎬 <b>Готовое смонтированное видео:</b>\n\n"
            f"⏱ <b>Хронометраж:</b> {orig_fmt} ➔ <b>{cut_fmt}</b> (сэкономлено {saved_str})\n"
            f"✂️ <b>Монтаж:</b> вырезано {stats['cuts_count']} пауз (30ms afade) + <b>Reels Punch-Cut</b> (чередование планов 1.00x ➔ 1.21x)\n"
            f"💬 <b>Субтитры:</b> Remotion Pro (пружины spring, Frosted Glass pill, неоновое золото, Callout-плашки)\n"
            f"🎞 <b>B-Roll перебивки:</b> {broll_status}\n"
            f"🔊 <b>Звук:</b> нормализован до -14 LUFS (Stereo 48kHz)\n"
            f"🎨 <b>Цвет:</b> Apple QuickTime MOV (сохранен оригинальный профиль)"
        )

        await progress.update(
            96,
            "📤 Отправка готового MOV в Telegram без сжатия...",
            force=True
        )

        if not final_mov.exists() or final_mov.stat().st_size == 0:
            raise FileNotFoundError(f"Финальный видеофайл не найден: {final_mov}")

        raw_stem = video_path.stem
        clean_stem = re.sub(r"^temp_[a-zA-Z0-9]+_[a-zA-Z0-9]+_", "", raw_stem)
        if not clean_stem or clean_stem.startswith("temp_"):
            clean_stem = "Reels"
        out_doc_name = f"Amalia_Reels_{clean_stem}.mov"

        thread_id = message.message_thread_id
        await message.bot.send_document(
            chat_id=message.chat.id,
            message_thread_id=thread_id,
            document=FSInputFile(str(final_mov), filename=out_doc_name),
            caption=video_caption,
            parse_mode="HTML"
        )

        await progress.finish()

        # Send agent explanation ONLY if user explicitly requested it in caption
        if user_wants_analysis and response:
            await send_formatted_response(message, None, response, model_name=model_name)

    except Exception as e:
        logger.error(f"Error in process_and_render_video: {e}", exc_info=True)
        progress.stop_ticker()
        if progress.msg_handle:
            try:
                await progress.msg_handle.edit_text(f"⚠️ Ошибка обработки видео: {e}")
            except Exception:
                await message.answer(f"⚠️ Ошибка обработки видео: {e}")
        else:
            await message.answer(f"⚠️ Ошибка обработки видео: {e}")
    finally:
        progress.stop_ticker()
        shutil.rmtree(edit_dir, ignore_errors=True)
        if video_path.exists():
            try:
                video_path.unlink()
            except Exception:
                pass


@router.message(F.video | F.video_note)
async def handle_video(message: types.Message):
    video_obj = message.video or message.video_note
    file_size = getattr(video_obj, "file_size", 0) or 0
    max_tg_size = 2000 * 1024 * 1024  # 2 GB limit for local Telegram Bot API

    if file_size > max_tg_size:
        size_mb = file_size / (1024 * 1024)
        await message.reply(
            f"⚠️ <b>Видео весит {size_mb:.1f} МБ — это превышает максимальный лимит Telegram (2 ГБ)!</b>\n\n"
            f"Пожалуйста, загрузите видео на Яндекс.Диск и пришлите ссылку сюда.",
            parse_mode="HTML"
        )
        return

    role, prompt = determine_role(message)
    target_role = "video_editor" if role in ("video_editor", "copywriter", "designer") else role

    size_mb = file_size / (1024 * 1024) if file_size else 0
    size_str = f" ({size_mb:.1f} МБ)" if size_mb > 0 else ""

    progress = VideoProgressBar(message)
    try:
        await progress.start(initial_text=f"📥 Скачивание видео{size_str}...")
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        temp_video_path = VIDEOS_DIR / f"temp_{video_obj.file_unique_id}_{uuid.uuid4().hex[:4]}.mov"
        await progress.update(10, f"📥 Скачивание видео{size_str}...", force=True)
        file_info = await message.bot.get_file(video_obj.file_id)
        await download_tg_file(message.bot, file_info.file_path, destination=temp_video_path)
        await process_and_render_video(
            message=message,
            video_path=temp_video_path,
            progress=progress,
            caption=message.caption or prompt or "",
            target_role=target_role
        )
    except Exception as e:
        logger.error(f"Error in handle_video: {e}", exc_info=True)
        if progress.msg_handle:
            try:
                await progress.msg_handle.edit_text(f"⚠️ Ошибка обработки видео: {e}")
            except Exception:
                pass
    finally:
        progress.stop_ticker()



@router.message(Command("video", "reels", "montage"))
async def cmd_video(message: types.Message):
    args = re.sub(r"^/(?:video|reels|montage)\s*", "", message.text or "", flags=re.IGNORECASE).strip()
    if not args:
        await message.answer(
            "🎬 <b>Видеомонтажер команды Амалии</b>\n\n"
            "• Пришлите видео или видео-кружок прямо в чат — я расшифрую его через ElevenLabs Scribe, найду паузы/оговорки, предложу нарезку и динамичные субтитры.\n"
            "• Или пришлите тему/текст: <code>/video [сценарий или тема рилса]</code> — я распишу покадровый план монтажа по ВИСП!",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer("🎬 <b>Видеомонтажер</b> готовит монтажный план...", parse_mode="HTML")
    response, model_name = await run_agent_task(role="video_editor", user_prompt=args)
    await send_formatted_response(message, wait_msg, response, model_name=model_name)


@router.message(Command("broll", "b_roll", "brolls"))
async def cmd_broll(message: types.Message):
    """Manage B-roll footage bank from Google Drive."""
    from tg_bot.engine.broll_manager import load_broll_config, list_broll_videos, async_sync_broll
    args = re.sub(r"^/(?:broll|b_roll|brolls)\s*", "", message.text or "", flags=re.IGNORECASE).strip()
    config = load_broll_config()
    current_url = config.get("drive_url", "")
    all_videos = list_broll_videos()

    if not args:
        url_text = f"<code>{current_url}</code>" if current_url else "<i>не подключена</i>"
        await message.answer(
            f"🎬 <b>Библиотека B-Roll футажей команды Амалии</b>\n\n"
            f"📁 <b>Папка Google Drive:</b> {url_text}\n"
            f"🎞 <b>Доступно видео-перебивок в банке:</b> {len(all_videos)} шт.\n\n"
            f"<b>Как подключить или обновить:</b>\n"
            f"1. Откройте доступ к папке на Google Диске: «Все, у кого есть ссылка» (Читатель).\n"
            f"2. Отправьте команду:\n"
            f"<code>/broll https://drive.google.com/drive/folders/...</code>\n"
            f"3. Для повторной синхронизации отправьте <code>/broll_sync</code>.",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer(
        "🔄 <b>Синхронизация библиотеки B-Roll из Google Drive...</b>\n"
        "<i>Скачиваю видеофайлы в локальный банк...</i>",
        parse_mode="HTML"
    )
    ok, status_text, count = await async_sync_broll(drive_url=args)
    if ok:
        await wait_msg.edit_text(
            f"✅ <b>Библиотека B-Roll успешно обновлена!</b>\n\n"
            f"🎞 <b>Всего футажей в банке:</b> {count} шт.\n"
            f"Теперь при монтаже Reels бот будет автоматически врезать 1–2 контекстные перебивки в видеопоток!",
            parse_mode="HTML"
        )
    else:
        await wait_msg.edit_text(
            f"⚠️ <b>Не удалось синхронизировать папку:</b>\n{status_text}\n\n"
            f"Убедитесь, что в настройках доступа Google Drive выбрано: <b>«Все, у кого есть ссылка — Читатель»</b>.",
            parse_mode="HTML"
        )


@router.message(Command("broll_sync"))
async def cmd_broll_sync(message: types.Message):
    """Trigger B-roll sync with existing URL."""
    from tg_bot.engine.broll_manager import load_broll_config, async_sync_broll
    config = load_broll_config()
    current_url = config.get("drive_url", "")
    if not current_url:
        await message.answer(
            "⚠️ <b>Ссылка на Google Drive еще не задана.</b>\n\n"
            "Используйте команду:\n<code>/broll https://drive.google.com/drive/folders/...</code>",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer("🔄 <b>Синхронизация библиотеки B-Roll из Google Drive...</b>", parse_mode="HTML")
    ok, status_text, count = await async_sync_broll(current_url)
    if ok:
        await wait_msg.edit_text(
            f"✅ <b>Библиотека B-Roll синхронизирована!</b>\n"
            f"🎞 В банке доступно: <b>{count} видео</b>",
            parse_mode="HTML"
        )
    else:
        await wait_msg.edit_text(f"⚠️ {status_text}", parse_mode="HTML")


@router.message(Command("adapt", "remake"))
async def cmd_adapt(message: types.Message):
    args = message.text.replace("/adapt", "").replace("/remake", "").strip()
    if not args:
        await message.answer(
            "🎨 <b>Отправьте текст или скриншот чужой карусели</b>\n\n"
            "Пример: <code>/adapt [текст карусели конкурента]</code>\n"
            "Или просто пришлите скриншоты в ветку <b>🎨 Дизайнер</b>.\n"
            "Конвейер (Копирайтер → Главред → Дизайнер) возьмет хук, перепишет голосом Амалии и сверстает готовый альбом PNG 1080x1350!",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer("🔄 <b>Запуск конвейера адаптации:</b> Копирайтер → Главред...", parse_mode="HTML")
    
    async def update_status(text: str):
        try:
            await status_msg.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

    clean_post_text, draft_id, model_name = await generate_carousel_draft(
        topic="Адаптация карусели конкурента под голос Амалии",
        source_text=args,
        status_callback=update_status
    )

    try:
        await status_msg.delete()
    except Exception:
        pass

    formatted_html = markdown_to_telegram_html(clean_post_text)
    await message.answer(
        f"✅ <b>Карусель адаптирована и проверена Главредом!</b>\n\n{formatted_html}\n\n<i>👇 Нажмите кнопку ниже, чтобы Дизайнер собрал карточки 1080x1350:</i>",
        parse_mode="HTML",
        reply_markup=get_carousel_keyboard(draft_id)
    )

@router.message(F.photo)
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    caption = (message.caption or "").strip()
    role, prompt = determine_role(message)

    # 0. User is uploading custom photo for a pending carousel draft
    if message.from_user and message.from_user.id in USER_PHOTO_WAIT_STATES:
        draft_id = USER_PHOTO_WAIT_STATES.pop(message.from_user.id)
        p_msg = USER_PHOTO_PROMPT_MSGS.pop(message.from_user.id, None)
        if p_msg:
            try:
                await p_msg.delete()
            except Exception:
                pass

        draft = get_draft(draft_id)
        if draft:
            file_info = await message.bot.get_file(photo.file_id)
            img_bytes_io = io.BytesIO()
            await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
            image_bytes = img_bytes_io.getvalue()
            
            photos_dir = KARUSEL_DIR / "photos"
            photos_dir.mkdir(parents=True, exist_ok=True)
            custom_photo_path = photos_dir / f"custom_{draft_id}.jpg"
            custom_photo_path.write_bytes(image_bytes)

            status_msg = await message.answer("🎨 <b>[Дизайнер]</b> Вставляет фото и верстает карточки 1080x1350...", parse_mode="HTML")
            
            async def update_status(text: str):
                try:
                    await status_msg.edit_text(text, parse_mode="HTML")
                except Exception:
                    pass

            success, log, images, deck_name, model_name = await render_carousel_from_text(
                text=draft["text"],
                topic=draft.get("topic", "Карусель"),
                status_callback=update_status,
                custom_photo_path=custom_photo_path
            )
            
            try:
                await status_msg.delete()
            except Exception:
                pass

            if images:
                await send_media_group_safe(message, images)
                kb_change = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📸 Заменить фото на финальном слайде", callback_data=f"render_photo_wait:{draft_id}")]
                ])
                await message.answer("✅ <b>Карточки с новым фото готовы!</b>", parse_mode="HTML", reply_markup=kb_change)
                return

    # 0.1 Отправка фото с готовым текстом карусели прямо в подписи (caption)
    is_caption_ready = any(k in caption.lower() for k in ["слайд 1", "слайд 2", "обложка:", "1 слайд", "1.", "2.", "3.", "слайд 3", "слайд 4"]) and len(caption.split("\n")) >= 3
    if is_caption_ready:
        file_info = await message.bot.get_file(photo.file_id)
        img_bytes_io = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
        image_bytes = img_bytes_io.getvalue()
        
        draft_id = save_draft(topic="Пользовательская карусель", text=caption)
        photos_dir = KARUSEL_DIR / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        custom_photo_path = photos_dir / f"custom_{draft_id}.jpg"
        custom_photo_path.write_bytes(image_bytes)

        status_msg = await message.answer("🎨 <b>[Дизайнер]</b> Размещает готовый текст и ставит ваше фото в финальный слайд...", parse_mode="HTML")
        
        async def update_status(text: str):
            try:
                await status_msg.edit_text(text, parse_mode="HTML")
            except Exception:
                pass

        success, log, images, deck_name, model_name = await render_carousel_from_text(
            text=caption,
            topic="Пользовательская карусель",
            status_callback=update_status,
            custom_photo_path=custom_photo_path
        )
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        if images:
            await send_media_group_safe(message, images)
            kb_change = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📸 Заменить фото на финальном слайде", callback_data=f"render_photo_wait:{draft_id}")]
            ])
            await message.answer("✅ <b>Карточки с вашим фото готовы!</b>", parse_mode="HTML", reply_markup=kb_change)
            return

    # 1. Загрузка фото Амалии в общий пул
    if caption.startswith("/photo") or caption.lower() in ("фото", "добавь фото", "сохрани фото", "фото амалии"):
        file_info = await message.bot.get_file(photo.file_id)
        img_bytes_io = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
        image_bytes = img_bytes_io.getvalue()
        
        photos_dir = KARUSEL_DIR / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        import time
        file_name = f"amalia_{int(time.time())}.jpg"
        (photos_dir / file_name).write_bytes(image_bytes)
        
        await message.answer(
            f"✅ <b>Фотография Амалии успешно добавлена в пул!</b>\n"
            f"Файл сохранен: <code>{file_name}</code>\n\n"
            f"Теперь Дизайнер сможет использовать эту фотографию для финальных слайдов каруселей.",
            parse_mode="HTML"
        )
        return

    # 2. Адаптация карусели конкурента
    if role in ("designer", "karusel") or any(w in caption.lower() for w in ("адаптир", "переделай", "карусель", "амали")):
        status_msg = await message.answer("🔄 <b>Запуск конвейера карусели:</b> Копирайтер → Главред...", parse_mode="HTML")
        
        async def update_status(text: str):
            try:
                await status_msg.edit_text(text, parse_mode="HTML")
            except Exception:
                pass

        file_info = await message.bot.get_file(photo.file_id)
        img_bytes_io = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
        image_bytes = img_bytes_io.getvalue()

        clean_post_text, draft_id, model_name = await generate_carousel_draft(
            topic="Адаптация карточки/карусели конкурента под голос Амалии",
            source_text=caption or "Адаптируй этот скриншот под стандарты блога Амалии Саргсян.",
            image_bytes=image_bytes,
            status_callback=update_status
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        formatted_html = markdown_to_telegram_html(clean_post_text)
        await message.answer(
            f"✅ <b>Карусель адаптирована и проверена Главредом!</b>\n\n{formatted_html}\n\n<i>👇 Нажмите кнопку ниже, чтобы Дизайнер собрал карточки 1080x1350:</i>",
            parse_mode="HTML",
            reply_markup=get_carousel_keyboard(draft_id)
        )
        return

    # Standard photo analysis
    wait_msg = await message.answer("🖼 Анализирую изображение/скриншот...", parse_mode="HTML")
    file_info = await message.bot.get_file(photo.file_id)
    img_bytes_io = io.BytesIO()
    await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
    image_bytes = img_bytes_io.getvalue()
    
    if not prompt:
        prompt = "Проанализируй этот скриншот/изображение с точки зрения контента, маркетинга и смыслов проекта."
    
    response, model_name = await run_agent_task(
        role=role,
        user_prompt=prompt,
        image_bytes=image_bytes,
        mime_type="image/jpeg"
    )
    
    await send_formatted_response(message, wait_msg, response, model_name=model_name)

