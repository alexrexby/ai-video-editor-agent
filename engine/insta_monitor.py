import os
import re
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Tuple, Optional, List

import instaloader
from tg_bot.config import BASE_DIR, MATERIALS_DIR
from tg_bot.engine.agent_runner import run_agent_task
from tg_bot.engine.carousel_builder import remake_competitor_carousel

INSTA_DIR = MATERIALS_DIR / "Instagram"
INSTA_DIR.mkdir(parents=True, exist_ok=True)

def is_instagram_url(text: str) -> bool:
    """Checks if text contains an Instagram link."""
    return bool(re.search(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv|stories)/[a-zA-Z0-9_\-]+", text))

def extract_instagram_url(text: str) -> Optional[str]:
    match = re.search(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv|stories)/[a-zA-Z0-9_\-]+[^\s]*", text)
    if match:
        return match.group(0)
    return None

def extract_shortcode(url: str) -> Optional[str]:
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_\-]+)", url)
    if match:
        return match.group(1)
    return None

def download_post_sync(shortcode: str, target_dir: Path):
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern=""
    )
    post = instaloader.Post.from_shortcode(L.context, shortcode)
    L.download_post(post, target=target_dir)
    return post.is_video, post.caption or ""

async def analyze_instagram_post(url: str) -> Tuple[str, str, List[Path]]:
    """
    Downloads Instagram Reel OR Carousel/Post, adapts it and prepares content:
    - If video: transcribes and generates Telegram post & insights.
    - If carousel/photos: OCRs slides, rewrites in Amalia's voice, and renders 1080x1350 PNG cards!
    Returns (response_text, model_name, generated_images_list).
    """
    shortcode = extract_shortcode(url)
    if not shortcode:
        return (
            "⚠️ Не удалось распознать ссылку на публикацию Instagram.",
            "Instagram Engine",
            []
        )

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        
        try:
            is_video, caption = await asyncio.to_thread(download_post_sync, shortcode, tmp_dir)
        except Exception as e:
            # Fallback to yt-dlp if instaloader hit rate limit
            return await fallback_ytdlp_process(url, tmp_dir)

        # 1. Handle Photo Carousel (NOT a video)
        jpg_files = sorted(list(tmp_dir.glob("*.jpg")))
        mp4_files = sorted(list(tmp_dir.glob("*.mp4")))

        if not is_video or (jpg_files and not mp4_files):
            # This is an image carousel! Adapt it to Amalia's brand & compile to PNG cards!
            first_image_bytes = jpg_files[0].read_bytes() if jpg_files else None
            
            source_content = f"Подпись к посту:\n{caption}\n\nКоличество карточек в оригинале: {len(jpg_files)}"
            
            success, log, images, deck_name, model_name, explanation = await remake_competitor_carousel(
                source_text=source_content,
                image_bytes=first_image_bytes
            )
            
            summary_text = (
                f"🎨 <b>Карусель из Instagram успешно адаптирована под Амалию!</b>\n\n"
                f"{explanation}\n\n"
                f"🖼 Сверстано карточек: <b>{len(images)}</b> (1080x1350 PNG)"
            )
            return summary_text, model_name, images

        # 2. Handle Video / Reels
        # Convert mp4 to mp3 audio for fast AI processing
        audio_path = tmp_dir / "audio.mp3"
        video_path = mp4_files[0] if mp4_files else None
        
        if video_path and video_path.exists():
            cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "libmp3lame", str(audio_path)]
            subprocess.run(cmd, capture_output=True)
            
        if not audio_path.exists():
            return "⚠️ Не удалось извлечь аудиодорожку из видео.", "Instagram Engine", []

        audio_bytes = audio_path.read_bytes()
        
        prompt = (
            f"Это расшифровка Reels / видео из Instagram (URL: {url}).\n"
            f"Оригинальный текст подписи: {caption}\n\n"
            "Сделай структурированный разбор для команды по формату:\n"
            "1. 💡 КЛЮЧЕВОЙ СМЫСЛ И БОЛЬ ЦА (в чём суть и какой вывод закладывается)\n"
            "2. 💬 ЖИВЫЕ ЦИТАТЫ АМАЛИИ (хлёсткие фразы, бытовые образы, добивки)\n"
            "3. ✍️ ГОТОВЫЙ ПОСТ ДЛЯ TELEGRAM-КАНАЛА (адаптируй этот рилс в полноценный пост для канала «вся правда о бьюти бизнесе» по правилам Урока 6)\n"
            "4. 🎨 ИДЕЯ ДЛЯ КАРУСЕЛИ (заголовок обложки, 3 слайда с тезисами, 1 CTA)"
        )
        
        response, model_name = await run_agent_task(
            role="analyst",
            user_prompt=prompt,
            audio_bytes=audio_bytes,
            mime_type="audio/mp3"
        )
        
        save_file = INSTA_DIR / f"Insta_Разбор_{shortcode}.md"
        try:
            save_file.write_text(f"# Разбор Reels: {url}\n\n{response}", encoding="utf-8")
        except Exception:
            pass
            
        return response, model_name, []

async def fallback_ytdlp_process(url: str, tmp_dir: Path) -> Tuple[str, str, List[Path]]:
    output_template = str(tmp_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", output_template,
        "--no-playlist",
        "--no-warnings",
        url
    ]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        mp3_files = list(tmp_dir.glob("*.mp3"))
        if mp3_files:
            audio_bytes = mp3_files[0].read_bytes()
            response, model_name = await run_agent_task(
                role="analyst",
                user_prompt=f"Расшифруй и разложи этот Reels из Instagram ({url}) на смыслы, цитаты, пост в Telegram и идею карусели.",
                audio_bytes=audio_bytes,
                mime_type="audio/mp3"
            )
            return response, model_name, []
        return f"⚠️ Не удалось загрузить медиа по ссылке:\n<code>{stderr.decode('utf-8', errors='ignore')[:300]}</code>", "Instagram Engine", []
    except Exception as e:
        return f"⚠️ Ошибка: {e}", "Instagram Engine", []
