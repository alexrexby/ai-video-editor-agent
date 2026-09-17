import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENGINE_DIR = Path(__file__).resolve().parent
FONTS_DIR = ENGINE_DIR / "fonts"
TEMP_DIR = BASE_DIR / "temp_render"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)

# FFmpeg
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "/opt/homebrew/bin/ffprobe")

# API Keys & Endpoints
POLZA_API_KEY = os.getenv("POLZA_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.polza.ai/api/v1")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "openai/whisper-1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

# Video Specs
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30

# Colors & Themes for "Glass" style
GLASS_PALETTES = {
    "amber": {
        "active_color": (255, 230, 0, 255),       # #FFE600
        "glow_color": (255, 180, 0, 180),
        "name": "Янтарь"
    },
    "azure": {
        "active_color": (42, 111, 219, 255),      # #2A6FDB
        "glow_color": (0, 150, 255, 180),
        "name": "Лазурь"
    },
    "lime": {
        "active_color": (0, 230, 118, 255),       # #00E676
        "glow_color": (0, 200, 80, 180),
        "name": "Лайм"
    },
    "crimson": {
        "active_color": (255, 46, 99, 255),       # #FF2E63
        "glow_color": (220, 20, 60, 180),
        "name": "Багряный"
    }
}

INACTIVE_COLOR = (255, 255, 255, 255)
STROKE_COLOR = (15, 15, 20, 240)
GLASS_BG_COLOR = (18, 16, 26, 175)              # Semi-transparent dark glass
GLASS_BORDER_COLOR = (255, 255, 255, 45)
