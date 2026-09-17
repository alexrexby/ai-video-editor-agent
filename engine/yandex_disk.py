import re
import urllib.parse
import aiohttp
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def is_yandex_disk_url(text: str) -> bool:
    return bool(re.search(r'https?://(?:disk\.yandex\.[a-z]+|yadi\.sk)/[^\s]+', text))

def extract_yandex_disk_url(text: str) -> str | None:
    match = re.search(r'https?://(?:disk\.yandex\.[a-z]+|yadi\.sk)/[^\s]+', text)
    return match.group(0) if match else None

async def download_yandex_disk_file(public_url: str, dest_dir: Path) -> tuple[bool, Path | None, str]:
    """
    Downloads a public file from Yandex Disk directly without authentication.
    Returns: (success, target_path, error_message)
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        encoded_url = urllib.parse.quote(public_url, safe="")
        api_url = f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={encoded_url}"
        
        timeout = aiohttp.ClientTimeout(total=600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Get file name from metadata
            meta_api = f"https://cloud-api.yandex.net/v1/disk/public/resources?public_key={encoded_url}"
            file_name = "yandex_downloaded_file.mp4"
            async with session.get(meta_api) as meta_resp:
                if meta_resp.status == 200:
                    meta_data = await meta_resp.json()
                    file_name = meta_data.get("name", file_name)

            # 2. Get direct download href
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    try:
                        err = await resp.json()
                        msg = err.get("message", f"Ошибка Яндекс.Диска ({resp.status})")
                    except Exception:
                        msg = f"Ошибка Яндекс.Диска ({resp.status})"
                    return False, None, msg
                
                data = await resp.json()
                download_href = data.get("href")
                if not download_href:
                    return False, None, "Не удалось получить ссылку на скачивание."

            # 3. Download direct stream to disk
            target_path = dest_dir / file_name
            async with session.get(download_href) as dl_resp:
                if dl_resp.status != 200:
                    return False, None, f"Ошибка загрузки файла ({dl_resp.status})"
                with open(target_path, "wb") as f:
                    while chunk := await dl_resp.content.read(1024 * 1024):
                        f.write(chunk)

            return True, target_path, ""
    except Exception as e:
        logger.error(f"Error downloading from Yandex Disk: {e}", exc_info=True)
        return False, None, str(e)
