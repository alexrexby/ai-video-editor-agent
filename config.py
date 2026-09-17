import os
import sys
from pathlib import Path

# Current module directory and base project directory
CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR

# Ensure CURRENT_DIR and parent directories are in sys.path
for p in [str(CURRENT_DIR), str(CURRENT_DIR.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load .env file safely
try:
    from dotenv import load_dotenv
    if (CURRENT_DIR / ".env").exists():
        load_dotenv(CURRENT_DIR / ".env")
    elif (CURRENT_DIR.parent / ".env").exists():
        load_dotenv(CURRENT_DIR.parent / ".env")
except ImportError:
    for env_candidate in [CURRENT_DIR / ".env", CURRENT_DIR.parent / ".env"]:
        if env_candidate.exists():
            for line in env_candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            break

# API Tokens and Endpoints (Configured via .env)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
POLZA_API_KEY = os.getenv("POLZA_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.polza.ai/api/v1")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "anthropic/claude-sonnet-4.5")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "http://127.0.0.1:8081")
USE_LOCAL_BOT_API = os.getenv("USE_LOCAL_BOT_API", "false").lower() in ("true", "1", "yes")

# Remotion directory resolution
_env_remotion = os.getenv("REMOTION_DIR", "")
if _env_remotion and Path(_env_remotion).exists():
    REMOTION_DIR = Path(_env_remotion)
elif (CURRENT_DIR / "remotion").exists():
    REMOTION_DIR = CURRENT_DIR / "remotion"
elif Path("/root/amalia_remotion").exists():
    REMOTION_DIR = Path("/root/amalia_remotion")
else:
    REMOTION_DIR = CURRENT_DIR / "remotion"

# Directory mappings
DATA_DIR = BASE_DIR / "data"
MATERIALS_DIR = os.getenv("MATERIALS_DIR", str(DATA_DIR / "materials"))
RAZBOR_DIR = os.getenv("RAZBOR_DIR", str(DATA_DIR / "razbors"))
CONTENT_DIR = os.getenv("CONTENT_DIR", str(DATA_DIR / "content"))
KARUSEL_DIR = os.getenv("KARUSEL_DIR", str(DATA_DIR / "carousels"))
VIDEOS_DIR = Path(os.getenv("VIDEOS_DIR", str(DATA_DIR / "videos")))
AGENTS_MD_PATH = BASE_DIR / "AGENTS.md"

MATERIALS_DIR = Path(MATERIALS_DIR)
RAZBOR_DIR = Path(RAZBOR_DIR)
CONTENT_DIR = Path(CONTENT_DIR)
KARUSEL_DIR = Path(KARUSEL_DIR)

for d in [DATA_DIR, MATERIALS_DIR, RAZBOR_DIR, CONTENT_DIR, KARUSEL_DIR, VIDEOS_DIR]:
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
