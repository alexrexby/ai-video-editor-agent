import subprocess
import requests
from pathlib import Path
from typing import Dict, Any, List
from .config import FFMPEG_PATH, POLZA_API_KEY, AI_BASE_URL, WHISPER_MODEL, TEMP_DIR

class Transcriber:
    """Extracts audio and transcribes speech with word-level timestamps using Whisper."""

    def __init__(self, api_key: str = POLZA_API_KEY, base_url: str = AI_BASE_URL, model: str = WHISPER_MODEL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def extract_audio(self, video_path: Path, output_wav: Path = None) -> Path:
        """Extracts mono 16kHz WAV audio from video using FFmpeg."""
        if output_wav is None:
            output_wav = TEMP_DIR / f"{video_path.stem}_audio.wav"

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_wav)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction failed: {res.stderr.decode('utf-8', errors='ignore')}")
        return output_wav

    def transcribe(self, audio_path: Path) -> Dict[str, Any]:
        """Transcribes audio file and returns text and word-level timestamps."""
        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/wav")}
            data = {
                "model": self.model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word"
            }
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)

        if resp.status_code != 200:
            raise RuntimeError(f"Whisper API error ({resp.status_code}): {resp.text}")

        result = resp.json()
        raw_words = result.get("words", [])
        
        # Normalize words (clean up spaces and punctuation)
        cleaned_words = []
        for item in raw_words:
            w_text = item.get("word", "").strip()
            if not w_text:
                continue
            cleaned_words.append({
                "word": w_text,
                "start": float(item.get("start", 0.0)),
                "end": float(item.get("end", 0.0))
            })

        return {
            "text": result.get("text", "").strip(),
            "duration": float(result.get("duration", 0.0)),
            "words": cleaned_words
        }
