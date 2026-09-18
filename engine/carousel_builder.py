try:
    from config import EXPERT_NAME, BRAND_NAME
except ImportError:
    EXPERT_NAME = os.getenv("EXPERT_NAME", "Эксперт")
    BRAND_NAME = os.getenv("BRAND_NAME", "AI Video Team")
import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path
from tg_bot.config import KARUSEL_DIR

AVAILABLE_DECKS = [
    "voda", "sobraniya", "kreslo", "opytny", "smenili", "ne_prodaet",
    "zerkalo", "silnye", "stabilizaciya", "sostoyanie", "progibaetes",
    "procent", "poteri", "upravlyayushchaya", "baza", "adaptaciya"
]

def extract_json_slides(text: str) -> list[dict] | None:
    """Extracts JSON array from agent response."""
    try:
        match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        match_raw = re.search(r'(\[\s*\{.*\}\s*\])', text, re.DOTALL)
        if match_raw:
            return json.loads(match_raw.group(1))
    except Exception:
        pass
    return None

DRAFTS_DIR = Path(__file__).parent.parent / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

def save_draft(topic: str, text: str, source_text: str = "") -> str:
    draft_id = str(int(time.time() * 1000))
    data = {
        "draft_id": draft_id,
        "topic": topic,
        "text": text,
        "source_text": source_text,
        "created_at": time.time()
    }
    (DRAFTS_DIR / f"{draft_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft_id

def get_draft(draft_id: str) -> dict | None:
    path = DRAFTS_DIR / f"{draft_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

async def update_draft_with_instructions(
    draft_id: str,
    instructions: str,
    status_callback=None
) -> tuple[str, str]:
    """
    Applies user edits / revisions to an existing carousel draft.
    Returns (updated_clean_text, draft_id).
    """
    draft = get_draft(draft_id)
    if not draft:
        return "", draft_id

    from tg_bot.engine.agent_runner import run_agent_task

    if status_callback:
        await status_callback("✏️ <b>[Главред]</b> Вносит правки в текст карусели...")

    edit_prompt = (
        f"Ты — Главный редактор проекта {BRAND_NAME}.\n"
        f"Перед тобой текущий текст карусели:\n\n"
        f"{draft['text']}\n\n"
        f"ПОЛЬЗОВАТЕЛЬ ПРОСИТ ВНЕСТИ СЛЕДУЮЩИЕ ПРАВКИ:\n"
        f"{instructions}\n\n"
        f"ТВОЯ ЗАДАЧА:\n"
        f"1. Аккуратно примени запрошенные изменения (например, замени CTA, оффер, формулировку слайда).\n"
        f"2. Сохрани жесткие правила голоса эксперта (живая речь, без «не X, а Y», без клише, только дефис «-»).\n"
        f"3. Выдай ИТОГОВУЮ ВЫЧИЩЕННУЮ ВЕРСИЮ всех слайдов карусели целиком."
    )

    editor_res, _ = await run_agent_task(role="editor", user_prompt=edit_prompt)
    clean_post_text = editor_res
    if "Итоговая вычищенная версия" in clean_post_text:
        clean_post_text = clean_post_text.split("Итоговая вычищенная версия")[-1].strip(": \n")

    # Update draft in place
    draft["text"] = clean_post_text
    draft["updated_at"] = time.time()
    (DRAFTS_DIR / f"{draft_id}.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean_post_text, draft_id

async def generate_carousel_draft(
    topic: str,
    status_callback=None,
    source_text: str = "",
    image_bytes: bytes | None = None
) -> tuple[str, str, str]:
    """
    Executes draft generation:
    1. If user provided ready/verified text: keep it untouched without editing.
    2. If only a raw topic is provided: Copywriter drafts -> Editor checks.
    Returns (clean_text, draft_id, model_name).
    """
    from tg_bot.engine.agent_runner import run_agent_task

    full_input = (topic + "\n" + source_text).strip()
    is_ready_text = any(k in full_input.lower() for k in ["слайд 1", "слайд 2", "обложка:", "1 слайд", "1.", "2.", "3.", "слайд 3", "слайд 4"]) and len(full_input.split("\n")) >= 3

    if is_ready_text:
        # Готовый текст уже проверен пользователем — НЕ РЕДАКТИРУЕМ И НЕ МЕНЯЕМ
        if status_callback:
            await status_callback("✅ <b>Текст проверен</b>, передаю Дизайнеру на размещение...")

        draft_id = save_draft(topic="Пользовательская карусель", text=full_input, source_text=source_text)
        return full_input, draft_id, "User Verified Content"

    # Stage 1: Копирайтер (генерация с нуля по теме)
    if status_callback:
        await status_callback("✍️ <b>1/2 [Копирайтер]</b> Упаковывает смыслы и пишет текст карточек...")

    copywriter_prompt = (
        f"Ты — Копирайтер проекта {BRAND_NAME}.\n"
        f"Напиши сильный текст карусели (5-7 карточек) для блога по следующим вводным:\n\n"
        f"{topic}\n"
        f"{('ИСХОДНЫЙ МАТЕРИАЛ:\n' + source_text) if source_text else ''}\n\n"
        f"СТРУКТУРА КАРУСЕЛИ:\n"
        f"- Слайд 1: Обложка (вирусный хук и живой лид, БЕЗ отдельной цитаты/плашки внизу)\n"
        f"- Слайд 2: Проблема / синяя перебивка (бытовой образ, боль)\n"
        f"- Слайды 3-5: Разбор сути, правила или кейс с конкретикой\n"
        f"- Слайд 6: Финальный призыв (кодовое слово капсом, лид на бесплатный разбор/диагностику)\n\n"
        f"СТРОГИЕ ПРАВИЛА ГОЛОСА:\n"
        f"- Живая речь, бытовые примеры («считать чеки до ночи», «бояться сделать замечание админам»).\n"
        f"- СТРОЖАЙШИЙ ЗАПРЕТ: «не потому что X, а Y», «не значит X, а Y», «дело не в X, а в Y», «Знакомо?», «Что мы сделали?», «Итог:», «глухая операционка».\n"
        f"- Только дефис «-»."
    )

    copywriter_res, model_name = await run_agent_task(
        role="copywriter",
        user_prompt=copywriter_prompt,
        image_bytes=image_bytes,
        mime_type="image/jpeg" if image_bytes else None
    )

    # Stage 2: Главред
    if status_callback:
        await status_callback("🔍 <b>2/2 [Главред]</b> Проверяет факты, стоп-слова и голос эксперта...")

    editor_prompt = (
        f"Ты — Главный редактор и Факт-чекер проекта {BRAND_NAME}.\n"
        f"Перед тобой черновик карусели от копирайтера:\n\n"
        f"{copywriter_res}\n\n"
        f"ТВОЯ ЗАДАЧА:\n"
        f"1. Жестко проверь текст на соответствие голосу эксперта и правилам проекта:\n"
        f"   - Удали любые «не потому что X, а Y», «не значит X, а Y», «дело не в X, а в Y».\n"
        f"   - Удали инфобиз-клише: «Знакомо?», «Что мы сделали?», «Итог:», «глухая операционка», «рутинные задачи».\n"
        f"   - Замени все длинные тире («—») на короткие «-».\n"
        f"   - Проверь, чтобы не было выдуманных фактов или лобовых продаж курсов.\n"
        f"2. Выдай ИТОГОВУЮ ВЫЧИЩЕННУЮ ВЕРСИЮ слайдов карусели (готовый чистый текст каждого слайда)."
    )

    editor_res, _ = await run_agent_task(role="editor", user_prompt=editor_prompt)

    clean_post_text = editor_res
    if "Итоговая вычищенная версия" in clean_post_text:
        clean_post_text = clean_post_text.split("Итоговая вычищенная версия")[-1].strip(": \n")

    draft_id = save_draft(topic=topic, text=clean_post_text, source_text=source_text)
    return clean_post_text, draft_id, model_name

async def render_carousel_from_text(
    text: str,
    topic: str = "Карусель",
    status_callback=None,
    custom_photo_path: str | Path | None = None
) -> tuple[bool, str, list[Path], str, str]:
    """
    Executes Stage 3 (Designer):
    Translates approved text into JSON slides without altering content, and compiles PNG cards.
    """
    from tg_bot.engine.agent_runner import run_agent_task

    if status_callback:
        await status_callback("🎨 <b>[Дизайнер]</b> Размещает текст на карточки 1080x1350...")

    designer_prompt = (
        f"Ты — Дизайнер и Арт-директор проекта {BRAND_NAME}.\n"
        f"Перед тобой ГОТОВЫЙ И ПРОВЕРЕННЫЙ текст карусели:\n\n"
        f"{text}\n\n"
        f"ТВОЯ ЕДИНСТВЕННАЯ ЗАДАЧА:\n"
        f"Разместить этот текст на карточки 1080x1350 в виде валидного JSON-массива (типы: cover, break, list, cta).\n\n"
        f"СТРОЖАЙШИЕ ПРАВИЛА:\n"
        f"1. ЗАПРЕЩЕНО РЕДАКТИРОВАТЬ, ПЕРЕПИСЫВАТЬ ИЛИ УРЕЗАТЬ ТЕКСТ! Переноси все формулировки, слова и CTA ТОЧНО И ДОСЛОВНО как в исходнике.\n"
        f"2. В слайде 'cover' (обложка): используй ТОЛЬКО 'title' и 'lead' (без плашек с цитатами, если их нет в тексте).\n"
        f"3. В финальном слайде 'cta': поле 'word' ОБЯЗАНО содержать ТОЧНОЕ кодовое слово из текста слайда капсом (например 'word': 'СИСТЕМА').\n"
        f"4. Верни ТОЛЬКО валидный JSON-массив карточек в блоке ```json ... ``` без лишних слов."
    )

    designer_res, model_name = await run_agent_task(role="designer", user_prompt=designer_prompt)
    success, log, images, deck_name, _ = await compile_slides_to_png(
        ai_response=designer_res,
        topic=topic[:30],
        model_name=model_name,
        custom_photo_path=custom_photo_path
    )
    return success, log, images, deck_name, model_name

async def build_multiagent_carousel(
    topic: str,
    status_callback=None,
    source_text: str = "",
    image_bytes: bytes | None = None,
    custom_photo_path: str | Path | None = None
) -> tuple[bool, str, list[Path], str, str, str]:
    """Full 3-stage pipeline (for direct generation)."""
    clean_post_text, draft_id, model_name = await generate_carousel_draft(
        topic=topic,
        status_callback=status_callback,
        source_text=source_text,
        image_bytes=image_bytes
    )
    success, log, images, deck_name, _ = await render_carousel_from_text(
        text=clean_post_text,
        topic=topic,
        status_callback=status_callback,
        custom_photo_path=custom_photo_path
    )
    return success, log, images, deck_name, model_name, clean_post_text

async def build_dynamic_carousel(topic: str, status_callback=None) -> tuple[bool, str, list[Path], str, str, str]:
    return await build_multiagent_carousel(topic=topic, status_callback=status_callback)

async def remake_competitor_carousel(source_text: str = "", image_bytes: bytes = None, status_callback=None) -> tuple[bool, str, list[Path], str, str, str]:
    return await build_multiagent_carousel(
        topic="Адаптация карусели конкурента под голос эксперта",
        source_text=source_text,
        image_bytes=image_bytes,
        status_callback=status_callback
    )

async def compile_slides_to_png(
    ai_response: str,
    topic: str,
    model_name: str,
    custom_photo_path: str | Path | None = None
) -> tuple[bool, str, list[Path], str, str]:
    slides = extract_json_slides(ai_response)
    if not slides:
        return False, f"Не удалось извлечь структуру карусели:\n{ai_response[:500]}", [], topic, model_name

    # If custom photo is specified, assign it to CTA slide
    if custom_photo_path:
        photo_str = str(custom_photo_path)
        cta_found = False
        for sl in slides:
            if sl.get("type") == "cta":
                sl["photo"] = photo_str
                cta_found = True
        if not cta_found and len(slides) > 0:
            slides[-1]["photo"] = photo_str

    timestamp = int(time.time())
    custom_dir = KARUSEL_DIR / f"karusel_custom_{timestamp}"
    custom_dir.mkdir(parents=True, exist_ok=True)
    json_path = custom_dir / "deck.json"
    json_path.write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")

    script_path = KARUSEL_DIR / "build_karusel.py"
    cmd = [sys.executable, str(script_path), "--json", str(json_path), str(custom_dir)]

    try:
        res = subprocess.run(cmd, cwd=str(KARUSEL_DIR), capture_output=True, text=True, check=False)
        output = (res.stdout or "") + "\n" + (res.stderr or "")
        images = sorted(list(custom_dir.glob("*.png")))
        return (res.returncode == 0 and len(images) > 0), output, images, topic, model_name
    except Exception as e:
        return False, str(e), [], topic, model_name

def run_build_karusel(deck_name: str | None = None) -> tuple[bool, str, list[Path], str]:
    """Executes build_karusel.py for pre-built templates."""
    if not KARUSEL_DIR.exists():
        return False, f"Папка генератора {KARUSEL_DIR} не найдена.", [], ""
        
    script_path = KARUSEL_DIR / "build_karusel.py"
    if not script_path.exists():
        return False, f"Скрипт {script_path} не найден.", [], ""

    target_deck = "voda"
    if deck_name:
        clean_name = deck_name.strip().lower()
        matched = [d for d in AVAILABLE_DECKS if clean_name in d or d in clean_name]
        if matched:
            target_deck = matched[0]
        elif clean_name in AVAILABLE_DECKS:
            target_deck = clean_name
        else:
            target_deck = "voda"

    cmd = [sys.executable, str(script_path), target_deck]

    try:
        res = subprocess.run(cmd, cwd=str(KARUSEL_DIR), capture_output=True, text=True, check=False)
        output = (res.stdout or "") + "\n" + (res.stderr or "")
        cards_dir = KARUSEL_DIR / target_deck
        images = sorted(list(cards_dir.glob("*.png"))) if cards_dir.exists() else []
        return (res.returncode == 0 and len(images) > 0), output, images, target_deck
    except Exception as e:
        return False, str(e), [], target_deck
