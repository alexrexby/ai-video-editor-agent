"""Integration with ElevenLabs Scribe (Speech-to-Text with word-level timestamps and audio events).
Used by the Video Editor agent based on video-use principles.
"""

from __future__ import annotations

import os
import re
import json
import asyncio
import subprocess
import tempfile
import logging
from pathlib import Path
import requests

from tg_bot.config import ELEVENLABS_API_KEY

logger = logging.getLogger(__name__)

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"

FILLER_WORDS = {
    "эээ", "ммм", "эмм", "ааа", "ээ", "мм", "э", "эм", "амм", "гм", "хм", "кхм",
    "ну", "типа", "короче", "как бы", "в общем", "в целом", "собственно", "так сказать", "значит",
    "uh", "umm", "um", "ah", "er", "like"
}


def extract_audio_from_video(video_path: Path, output_wav: Path) -> Path:
    """Extracts mono 16kHz PCM audio suitable for ElevenLabs Scribe."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(output_wav)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_wav


def transcribe_audio_with_scribe(audio_path: Path, api_key: str = "") -> dict:
    """Calls ElevenLabs Scribe API with word-level timestamps and audio events."""
    key = api_key or ELEVENLABS_API_KEY
    if not key:
        raise ValueError("ELEVENLABS_API_KEY is not set.")

    headers = {
        "xi-api-key": key
    }
    data = {
        "model_id": "scribe_v1",
        "tag_audio_events": "true",
        "timestamps_granularity": "word"
    }

    with open(audio_path, "rb") as f:
        files = {"file": f}
        response = requests.post(SCRIBE_URL, headers=headers, files=files, data=data, timeout=300)

    if response.status_code != 200:
        logger.error(f"ElevenLabs Scribe failed ({response.status_code}): {response.text}")
        raise RuntimeError(f"ElevenLabs Scribe API error {response.status_code}: {response.text}")

    return response.json()


def format_seconds(seconds: float) -> str:
    """Converts seconds float to MM:SS.cc string."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"


def build_packed_transcript(scribe_data: dict, silence_gap_threshold: float = 0.4) -> str:
    """
    Builds a packed phrase-level transcript with exact timestamps,
    silence gaps, filler tags and audio events — the LLM's primary reading view.
    """
    words = scribe_data.get("words", [])
    if not words:
        return scribe_data.get("text", "")

    lines: list[str] = []
    current_phrase_words: list[dict] = []
    prev_end: float | None = None

    for item in words:
        item_type = item.get("type", "word")
        text = item.get("text", "").strip()
        start = item.get("start", 0.0)
        end = item.get("end", start)

        # Check for pause between words
        if prev_end is not None and (start - prev_end) >= silence_gap_threshold:
            gap = start - prev_end
            if current_phrase_words:
                p_start = current_phrase_words[0]["start"]
                p_end = current_phrase_words[-1]["end"]
                phrase_text = " ".join(w["text"] for w in current_phrase_words)
                lines.append(f"[{format_seconds(p_start)} -> {format_seconds(p_end)}] {phrase_text}")
                current_phrase_words = []
            lines.append(f"  ⏳ [ПАУЗА {gap:.2f}s]")

        # Mark audio events or filler words
        clean_word = re.sub(r"[^\wа-яА-ЯёЁa-zA-Z]", "", text.lower())
        if item_type == "audio_event":
            lines.append(f"  ⚡️ [ЗВУК: {text}]")
        elif clean_word in FILLER_WORDS:
            item["text"] = f"⚠️<{text}>"
            current_phrase_words.append(item)
        else:
            current_phrase_words.append(item)

        prev_end = end

    if current_phrase_words:
        p_start = current_phrase_words[0]["start"]
        p_end = current_phrase_words[-1]["end"]
        phrase_text = " ".join(w["text"] for w in current_phrase_words)
        lines.append(f"[{format_seconds(p_start)} -> {format_seconds(p_end)}] {phrase_text}")

    return "\n".join(lines)


def detect_cut_suggestions(scribe_data: dict) -> list[dict]:
    """
    Detects candidate cuts based on silence gaps >= 0.4s and filler words.
    """
    words = scribe_data.get("words", [])
    suggestions = []
    prev_end: float | None = None

    for idx, item in enumerate(words):
        start = item.get("start", 0.0)
        end = item.get("end", start)
        text = item.get("text", "")
        clean_word = re.sub(r"[^\wа-яА-ЯёЁa-zA-Z]", "", text.lower())

        if prev_end is not None and (start - prev_end) >= 0.4:
            gap = start - prev_end
            suggestions.append({
                "type": "silence",
                "start": prev_end,
                "end": start,
                "duration": gap,
                "description": f"Пауза {gap:.2f}s между словами"
            })

        if clean_word in FILLER_WORDS:
            suggestions.append({
                "type": "filler",
                "start": start,
                "end": end,
                "word": text,
                "description": f"Слово-паразит '{text}'"
            })

        prev_end = end

    return suggestions


async def async_transcribe_media(media_path: Path) -> tuple[dict, str, list[dict]]:
    """
    Full async pipeline:
    Extracts audio if needed -> calls ElevenLabs Scribe -> builds packed transcript + cut suggestions.
    """
    temp_wav = media_path.with_suffix(".temp.wav")
    try:
        # Check if media is video or audio
        suffix = media_path.suffix.lower()
        if suffix in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"]:
            await asyncio.to_thread(extract_audio_from_video, media_path, temp_wav)
            audio_file = temp_wav
        else:
            # Already audio (ogg, mp3, wav)
            await asyncio.to_thread(extract_audio_from_video, media_path, temp_wav)
            audio_file = temp_wav

        scribe_data = await asyncio.to_thread(transcribe_audio_with_scribe, audio_file)
        packed_text = build_packed_transcript(scribe_data)
        cuts = detect_cut_suggestions(scribe_data)

        return scribe_data, packed_text, cuts
    finally:
        if temp_wav.exists():
            try:
                temp_wav.unlink()
            except Exception:
                pass
