"""
B-Roll footage bank manager with Google Drive synchronization via gdown.
Caches video clips locally and provides B-roll segments for Reels editing.
"""
import asyncio
import json
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Determine B-Roll bank directory
try:
    from config import BROLL_DIR
except ImportError:
    _env_broll = os.getenv("BROLL_DIR", "")
    if _env_broll and Path(_env_broll).exists():
        BROLL_DIR = Path(_env_broll)
    else:
        BROLL_DIR = Path(__file__).resolve().parent.parent / "broll_bank"

BROLL_CONFIG_FILE = BROLL_DIR / "broll_config.json"
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def ensure_broll_dir() -> Path:
    BROLL_DIR.mkdir(parents=True, exist_ok=True)
    return BROLL_DIR


def load_broll_config() -> dict:
    ensure_broll_dir()
    if BROLL_CONFIG_FILE.exists():
        try:
            return json.loads(BROLL_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read broll config: {e}")
    return {"drive_url": os.getenv("GOOGLE_DRIVE_BROLL_URL", "")}


def save_broll_config(config: dict) -> None:
    ensure_broll_dir()
    try:
        BROLL_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save broll config: {e}")


def list_broll_videos() -> list[Path]:
    """Returns a list of all valid video files in the B-roll bank."""
    if not BROLL_DIR.exists():
        return []
    videos = []
    for item in BROLL_DIR.rglob("*"):
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
            if not item.name.startswith(".") and item.stat().st_size > 100_000:
                videos.append(item)
    return videos


def select_broll_clips(count: int = 1) -> list[Path]:
    """Randomly selects up to `count` video clips from the B-roll library."""
    all_videos = list_broll_videos()
    if not all_videos:
        return []
    if len(all_videos) <= count:
        return list(all_videos)
    return random.sample(all_videos, count)


def _sync_drive_worker(drive_url: str, target_dir: Path) -> tuple[bool, str, int]:
    """Synchronous worker that downloads files from Google Drive using gdown."""
    try:
        import gdown
        clean_url = drive_url.strip()
        logger.info(f"Starting Google Drive B-roll sync from {clean_url} to {target_dir}...")
        
        # Download folder contents
        downloaded = gdown.download_folder(
            url=clean_url,
            output=str(target_dir),
            quiet=False,
            use_cookies=False,
            remaining_ok=True
        )
        
        count = len(list_broll_videos())
        return True, f"Успешно синхронизировано. Всего видео в банке: {count}", count
    except Exception as e:
        logger.error(f"Google Drive B-roll sync failed: {e}", exc_info=True)
        return False, f"Ошибка синхронизации: {e}", len(list_broll_videos())


async def async_sync_broll(drive_url: str | None = None) -> tuple[bool, str, int]:
    """Asynchronous wrapper for Google Drive synchronization."""
    ensure_broll_dir()
    config = load_broll_config()
    target_url = drive_url or config.get("drive_url")
    if not target_url:
        return False, "Ссылка на папку Google Drive не задана. Используйте /broll <ссылка>", len(list_broll_videos())

    # Update config if new URL provided
    if drive_url and drive_url != config.get("drive_url"):
        config["drive_url"] = drive_url
        save_broll_config(config)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_drive_worker, target_url, BROLL_DIR)
