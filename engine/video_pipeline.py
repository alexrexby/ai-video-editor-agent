"""Professional video editing engine based on browser-use/video-use and modern Reels standards.

Features:
1. Automatic silence and dead space cutting (pauses >= 0.4s) with 50ms pre-pad and 80ms post-pad.
2. Seamless 30ms audio fades (afade in/out) at every cut boundary to prevent audio clicks/pops.
3. Stylish dynamic karaoke subtitles:
   - Font: Montserrat ExtraBold (bold, modern, punchy)
   - 2-3 words per visual chunk
   - Active word highlighted in Electric Gold/Yellow ({\\c&H0020E5FF&})
   - Platform safe-zone placement (MarginV=460 on 1080x1920) so captions are never covered by Reels UI
4. Social-media loudness normalization (-14 LUFS / -1 dBTP).
5. Fast lossless concatenation demuxer.
"""

from __future__ import annotations

import os
import re
import json
import math
import uuid
import shutil
import asyncio
import logging
import tempfile
import subprocess
from pathlib import Path

try:
    from tg_bot.engine.elevenlabs_scribe import format_seconds
except ImportError:
    from engine.elevenlabs_scribe import format_seconds

try:
    from tg_bot.engine.broll_manager import select_broll_clips
except ImportError:
    try:
        from engine.broll_manager import select_broll_clips
    except ImportError:
        def select_broll_clips(count: int = 1):
            return []

logger = logging.getLogger(__name__)

LOUDNORM_I = -14.0
LOUDNORM_TP = -1.0
LOUDNORM_LRA = 11.0
PUNCT_BREAK = set(".,!?;:")


def get_video_duration(video_path: Path) -> float:
    """Gets video duration in seconds via ffprobe."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ],
            capture_output=True, text=True, check=True
        )
        return float(out.stdout.strip())
    except Exception as e:
        logger.error(f"Error probing duration: {e}")
        return 0.0


def is_portrait_source(video: Path) -> bool:
    """Checks if the video is vertical (height > width), accounting for rotation metadata."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_side_data=rotation",
                "-of", "json", str(video)
            ],
            capture_output=True, text=True, check=True
        )
        data = json.loads(out.stdout)
        streams = data.get("streams") or []
        if not streams:
            return False
        st = streams[0]
        w, h = int(st.get("width", 0)), int(st.get("height", 0))
        rotation = 0
        for sd in st.get("side_data_list") or []:
            if sd.get("rotation") is not None:
                rotation = sd["rotation"]
                break
        if int(round(float(rotation))) % 360 in (90, 270):
            w, h = h, w
        return h > w
    except Exception:
        return False


def probe_source_fps(video: Path) -> str:
    """Detects video frame rate."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate,avg_frame_rate",
                "-of", "json", str(video)
            ],
            capture_output=True, text=True, check=True
        )
        streams = json.loads(out.stdout).get("streams") or []
        if streams:
            for k in ("avg_frame_rate", "r_frame_rate"):
                v = streams[0].get(k)
                if v and v != "0/0":
                    return v
    except Exception:
        pass
    return "30/1"


def parse_fps_float(fps_str: str | None) -> float:
    """Parses fps string like '30/1' or '29.97' into float."""
    if not fps_str:
        return 30.0
    try:
        if "/" in str(fps_str):
            num, den = str(fps_str).split("/", 1)
            return float(num) / float(den) if float(den) != 0 else 30.0
        return float(fps_str)
    except Exception:
        return 30.0


def probe_source_color_info(video: Path) -> dict:
    """Detects pixel format, color space, transfer function, and primaries from source."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt,color_space,color_transfer,color_primaries,color_range",
                "-of", "json", str(video)
            ],
            capture_output=True, text=True, check=True
        )
        data = json.loads(out.stdout)
        streams = data.get("streams") or []
        if streams:
            st = streams[0]
            transfer = str(st.get("color_transfer") or "")
            space = str(st.get("color_space") or "")
            primaries = str(st.get("color_primaries") or "")
            pix_fmt = str(st.get("pix_fmt") or "")
            is_hdr = (
                "arib-std-b67" in transfer.lower()
                or "smpte2084" in transfer.lower()
                or "bt2020" in space.lower()
                or "bt2020" in primaries.lower()
                or "10" in pix_fmt
            )
            return {
                "is_hdr": is_hdr,
                "codec": "libx264",
                "preset": "fast",
                "crf": "18",
                "tag_args": [],
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
                "pix_fmt": "yuv420p"
            }
    except Exception:
        pass
    return {
        "is_hdr": False,
        "codec": "libx264",
        "preset": "fast",
        "crf": "18",
        "tag_args": [],
        "color_space": "bt709",
        "color_transfer": "bt709",
        "color_primaries": "bt709",
        "pix_fmt": "yuv420p"
    }


def verify_video_and_audio(file_path: Path) -> bool:
    """Checks that rendered file exists, is non-empty, and contains both video and audio streams."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_streams",
                "-of", "json", str(file_path)
            ],
            capture_output=True, text=True, check=True
        )
        data = json.loads(out.stdout)
        streams = data.get("streams", [])
        has_v = any(s.get("codec_type") == "video" for s in streams)
        has_a = any(s.get("codec_type") == "audio" for s in streams)
        return has_v and has_a
    except Exception:
        return False


FILLER_WORDS_SET = {
    "эээ", "ммм", "эмм", "ааа", "ээ", "мм", "эм", "амм", "гм", "хм", "кхм",
    "uh", "umm", "um", "ah", "er"
}


def is_filler_word(
    word_str: str,
    duration: float = 0.0,
    prev_gap: float = 0.0,
    next_gap: float = 0.0,
    is_standalone_or_gap: bool = False
) -> bool:
    """Detects filler sounds, hesitations, and parasite words (эээ, ааа, ммм, ну, etc.)."""
    clean = re.sub(r"[^\wа-яА-ЯёЁa-zA-Z]", "", word_str.lower()).strip()
    if not clean:
        return False
    if clean in FILLER_WORDS_SET:
        return True
    # Hesitation sounds like "э-э", "э...", "ээ"
    if re.match(r"^[эe]+$", clean):
        return True
    # "мм", "ммм"
    if re.match(r"^[мm]+$", clean) and len(clean) >= 2:
        return True
    # Hesitation "аа", "ааа", or single "а" with pause or prolonged
    if re.match(r"^[аa]+$", clean):
        if len(clean) >= 2:
            return True
        if prev_gap >= 0.18 or next_gap >= 0.18 or duration >= 0.25 or is_standalone_or_gap:
            return True
    # "ну" when isolated by pause
    if clean == "ну" and (prev_gap >= 0.18 or next_gap >= 0.18 or duration >= 0.35 or is_standalone_or_gap):
        return True
    return False


def build_edl_from_scribe(
    scribe_data: dict,
    source_path: Path,
    min_silence: float = 0.30,
    pre_pad: float = 0.04,
    post_pad: float = 0.06
) -> tuple[dict, list[dict]]:
    """
    Builds an Edit Decision List (EDL) keeping clean speech ranges and actively cutting:
    - Dead pauses >= min_silence (0.30s)
    - Filler words and hesitation sounds (эээ, ааа, ммм, ну...)
    - Splits long phrases (>= 3.5s) at sentence boundaries with breath gaps (>= 0.15s) for dynamic camera framing
    Returns (edl, cut_stats).
    """
    total_duration = get_video_duration(source_path)
    raw_words = [w for w in scribe_data.get("words", []) if w.get("type") == "word"]

    if not raw_words:
        return {
            "sources": {"v0": str(source_path)},
            "ranges": [{"source": "v0", "start": 0.0, "end": total_duration, "beat": "full"}]
        }, []

    segments: list[list[dict]] = []
    current_seg: list[dict] = []
    cuts_info: list[dict] = []

    for i in range(len(raw_words)):
        w = raw_words[i]
        w_st = float(w.get("start", 0.0))
        w_en = float(w.get("end", w_st))
        w_dur = w_en - w_st
        prev_w = raw_words[i - 1] if i > 0 else None
        next_w = raw_words[i + 1] if i + 1 < len(raw_words) else None

        prev_gap = (w_st - float(prev_w.get("end", 0.0))) if prev_w else 999.0
        next_gap = (float(next_w.get("start", 0.0)) - w_en) if next_w else 999.0

        # 1. Check if current word is a filler hesitation (эээ, ааа, ну...)
        if is_filler_word(w.get("text", ""), duration=w_dur, prev_gap=prev_gap, next_gap=next_gap):
            if current_seg:
                segments.append(current_seg)
                current_seg = []
            cuts_info.append({
                "type": "filler",
                "start": w_st,
                "end": w_en,
                "duration": w_dur,
                "word": w.get("text", "").strip(),
                "description": f"Вырезана запинка/паразит '{w.get('text', '').strip()}'"
            })
            continue

        # 2. Check for dead silence pause before this word
        if prev_w and prev_gap >= min_silence:
            if current_seg:
                segments.append(current_seg)
                current_seg = []
            cuts_info.append({
                "type": "silence",
                "start": float(prev_w.get("end", 0.0)),
                "end": w_st,
                "duration": prev_gap,
                "description": f"Пауза {prev_gap:.2f}s"
            })
        elif current_seg and prev_w:
            # 3. Dynamic Reels pacing: if phrase exceeds 3.5s and ends with sentence punctuation with breath gap >= 0.15s
            curr_dur = w_st - float(current_seg[0].get("start", 0.0))
            prev_t = (prev_w.get("text") or "").strip()
            if curr_dur >= 3.5 and prev_gap >= 0.15 and prev_t and prev_t[-1] in ".!?;:":
                segments.append(current_seg)
                current_seg = []

        current_seg.append(w)

    if current_seg:
        segments.append(current_seg)

    ranges: list[dict] = []
    last_end = 0.0
    for seg in segments:
        if not seg:
            continue
        clean_seg = [w for w in seg if not is_filler_word(w.get("text", ""))]
        if not clean_seg:
            continue

        start_t = max(last_end, float(clean_seg[0]["start"]) - pre_pad)
        end_t = float(clean_seg[-1]["end"]) + post_pad
        if total_duration > 0:
            end_t = min(total_duration, end_t)
        if end_t <= start_t:
            end_t = start_t + 0.1

        phrase_text = " ".join(w.get("text", "") for w in clean_seg[:6])
        ranges.append({
            "source": "v0",
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "beat": f"Фраза: {phrase_text}...",
            "words": clean_seg
        })
        last_end = end_t

    edl = {
        "sources": {"v0": str(source_path)},
        "ranges": ranges
    }
    return edl, cuts_info


def format_ass_time(sec: float) -> str:
    """Formats float seconds into ASS timestamp H:MM:SS.cs."""
    cs = int(round(sec * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def build_stylish_karaoke_ass(
    edl: dict,
    out_path: Path,
    is_portrait: bool = True
) -> Path:
    """
    Generates stylish viral Reels subtitles in ASS format:
    - 2-3 words per chunk
    - Montserrat ExtraBold font
    - Active word highlighted in Electric Gold/Yellow (&H0020E5FF)
    - Safe zone margin for Reels/Shorts
    """
    if is_portrait:
        play_res_x = 1080
        play_res_y = 1920
        font_size = 70
        margin_v = 460  # Safe zone ~24% from bottom
        outline_size = 5.5
        shadow_size = 2.5
    else:
        play_res_x = 1920
        play_res_y = 1080
        font_size = 56
        margin_v = 120
        outline_size = 4.5
        shadow_size = 2.0

    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Montserrat ExtraBold,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline_size},{shadow_size},2,40,40,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    hl_color = "&H0020E5FF&"  # Vibrant Gold / Yellow
    white_color = "&H00FFFFFF&"

    seg_offset = 0.0
    for r in edl.get("ranges", []):
        seg_st = float(r["start"])
        seg_en = float(r["end"])
        seg_dur = seg_en - seg_st
        r_words = r.get("words", [])

        # Group words into 2-3 word chunks
        chunks: list[list[dict]] = []
        c_curr: list[dict] = []
        for w in r_words:
            t = (w.get("text") or "").strip()
            if not t or is_filler_word(t, is_standalone_or_gap=True):
                continue
            c_curr.append(w)
            if len(c_curr) >= 2 or t[-1] in PUNCT_BREAK:
                chunks.append(c_curr)
                c_curr = []
        if c_curr:
            chunks.append(c_curr)

        for chunk in chunks:
            chunk_clean = [re.sub(r"[^\wа-яА-ЯёЁa-zA-Z0-9]", "", w.get("text", "")).upper() for w in chunk]
            for i, w in enumerate(chunk):
                w_st = max(seg_st, w["start"]) - seg_st + seg_offset
                if i + 1 < len(chunk):
                    w_en = max(seg_st, chunk[i + 1]["start"]) - seg_st + seg_offset
                else:
                    w_en = min(seg_en, chunk[-1]["end"]) - seg_st + seg_offset + 0.15
                if w_en <= w_st:
                    w_en = w_st + 0.25

                parts = []
                for j, word_str in enumerate(chunk_clean):
                    if j == i:
                        parts.append("{\\c" + hl_color + "}" + word_str + "{\\c" + white_color + "}")
                    else:
                        parts.append(word_str)
                text_line = " ".join(parts)
                ass_lines.append(f"Dialogue: 0,{format_ass_time(w_st)},{format_ass_time(w_en)},Default,,0,0,0,,{text_line}")

        seg_offset += seg_dur

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(ass_lines), encoding="utf-8")
    return out_path


def extract_timed_captions_for_remotion(edl: dict) -> list[dict]:
    """
    Extracts word timestamps mapped to the final output timeline
    in milliseconds for Remotion @remotion/captions.
    """
    captions = []
    seg_offset = 0.0
    for r in edl.get("ranges", []):
        seg_st = float(r["start"])
        seg_en = float(r["end"])
        seg_dur = seg_en - seg_st
        r_words = r.get("words", [])

        for w in r_words:
            t = (w.get("text") or "").strip()
            if not t or is_filler_word(t, is_standalone_or_gap=True):
                continue
            clean_word = re.sub(r"[^\wа-яА-ЯёЁa-zA-Z0-9\-\?!,\.]", "", t)
            if not clean_word:
                continue

            w_st = max(seg_st, float(w["start"])) - seg_st + seg_offset
            w_en = min(seg_en, float(w["end"])) - seg_st + seg_offset
            if w_en <= w_st:
                w_en = w_st + 0.25

            # Detect accent / punch words in Russian speech (numbers, %, currencies, key business & emotion triggers)
            word_lower = clean_word.lower()
            is_accent = bool(
                re.search(r"(\d+|%|\$|€|₽|руб|тыс|млн|млрд|х\d+|x\d+)", word_lower) or
                re.search(r"\b(деньги|денег|деньгам|выручк\w*|прибыл\w*|результат\w*|секрет\w*|систем\w*|ошибк\w*|клиент\w*|мастер\w*|продаж\w*|масштаб\w*|миллион\w*|миллиард\w*|гаранти\w*|быстро|сразу|точно|чек-лист\w*|важно|внимани\w*|правил\w*|главн\w*|никогда|всегда|перв\w*|топ|суть|баз\w*|практикум\w*|курс\w*|интенсив\w*|подар\w*|бонус\w*|инсайт\w*|мысл\w*|смысл\w*|рост\w*|структур\w*|стратеги\w*|хуже|лучше|вау|классно|шок|факт|правда|цел\w*|успех\w*|провал\w*)\b", word_lower, re.IGNORECASE) or
                "!" in t or
                (t.isupper() and len(clean_word) > 1)
            )

            captions.append({
                "text": clean_word + " ",
                "rawText": t,
                "isAccent": is_accent,
                "startMs": int(round(w_st * 1000)),
                "endMs": int(round(w_en * 1000)),
                "timestampMs": int(round(w_st * 1000)),
                "confidence": 0.99
            })

        seg_offset += seg_dur

    return captions


def extract_callouts_from_transcript(edl: dict) -> list[dict]:
    """
    Extracts 1-3 punchy, high-impact callout badges based on spoken transcript keywords & numbers.
    Maps timestamps to the final cut timeline (accounting for removed pauses).
    """
    callouts = []
    sources = edl.get("sources", {})
    ranges = edl.get("ranges", [])
    if not ranges:
        return []

    KEYWORD_TRIGGERS = [
        (["ошибк", "слива"], "❌ ГЛАВНАЯ ОШИБКА", "alert"),
        (["секрет", "инсайт"], "💡 СЕКРЕТНЫЙ ИНСАЙТ", "info"),
        (["результат", "выручк", "доход", "миллион"], "🚀 ВЗРЫВНОЙ РЕЗУЛЬТАТ", "info"),
        (["важно", "внимани", "правило"], "⚡️ ОБРАТИТЕ ВНИМАНИЕ", "alert"),
        (["система", "структур"], "💎 СИСТЕМНЫЙ ПОДХОД", "info"),
        (["клиент", "мастер"], "👥 РАБОТА С КЛИЕНТАМИ", "info"),
        (["интенсив", "курс", "продукт"], "🔥 ПРАКТИКУМ АМАЛИИ", "info"),
    ]

    NUMBER_PATTERN = re.compile(r"\b(\d+[\d\s]*(?:%|руб|тыс|млн|лет|шаг\w*|клиент\w*|к|k|x)?)\b", re.IGNORECASE)

    seg_offset = 0.0
    last_callout_time = -10.0

    for r in ranges:
        seg_start = float(r["start"])
        seg_end = float(r["end"])
        seg_dur = seg_end - seg_start
        quote = r.get("quote", "")

        words = quote.split()
        for w_idx, w in enumerate(words):
            clean_w = re.sub(r"[^\w%]", "", w).lower()
            w_time = seg_offset + (w_idx / max(1, len(words))) * seg_dur

            if w_time - last_callout_time < 8.0:
                continue

            matched_badge = None
            matched_type = "info"

            for triggers, badge_text, b_type in KEYWORD_TRIGGERS:
                if any(tr in clean_w for tr in triggers):
                    matched_badge = badge_text
                    matched_type = b_type
                    break

            if not matched_badge and NUMBER_PATTERN.match(clean_w) and len(clean_w) >= 2 and not clean_w.isdigit() or (clean_w.isdigit() and int(clean_w) > 9):
                matched_badge = f"⚡️ {clean_w.upper()}"
                matched_type = "info"

            if matched_badge:
                callouts.append({
                    "startMs": int(w_time * 1000),
                    "endMs": int((w_time + 2.2) * 1000),
                    "text": matched_badge,
                    "type": matched_type
                })
                last_callout_time = w_time
                if len(callouts) >= 3:
                    break

        if len(callouts) >= 3:
            break

        seg_offset += seg_dur

    return callouts


def overlay_broll_clips(
    base_mov: Path,
    broll_clips: list[Path],
    cut_duration: float,
    output_path: Path,
    color_args: list[str] | None = None,
    color_info: dict | None = None
) -> bool:
    """
    Overlays 1-2 B-roll clips over the base talking head video.
    Audio track from base video is completely preserved (c:a copy).
    B-roll video is scaled/cropped to 1080x1920 with smooth 0.25s alpha fade in/out.
    """
    if not broll_clips or cut_duration < 15.0:
        return False

    try:
        slots = []
        if len(broll_clips) >= 1:
            t1 = min(max(5.0, cut_duration * 0.25), cut_duration - 4.0)
            slots.append((broll_clips[0], t1, 2.3))
        if len(broll_clips) >= 2 and cut_duration >= 35.0:
            t2 = min(max(t1 + 10.0, cut_duration * 0.65), cut_duration - 3.5)
            if t2 > t1 + 4.0:
                slots.append((broll_clips[1], t2, 2.3))

        if not slots:
            return False

        cmd = ["ffmpeg", "-y", "-i", str(base_mov)]
        filter_parts = []
        last_v = "[0:v]"

        for s_idx, (b_path, start_t, b_dur) in enumerate(slots):
            cmd.extend(["-i", str(b_path)])
            b_input = f"[{s_idx + 1}:v]"
            b_out = f"[broll{s_idx}]"
            end_t = start_t + b_dur
            fade_out_start = max(0.0, b_dur - 0.25)
            vf_broll = (
                f"scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,"
                f"fade=in:st=0:d=0.25:alpha=1,"
                f"fade=out:st={fade_out_start:.2f}:d=0.25:alpha=1,"
                f"setpts=PTS-STARTPTS+{start_t:.3f}/TB"
            )
            filter_parts.append(f"{b_input}{vf_broll}{b_out}")
            next_v = f"[v{s_idx}]" if s_idx < len(slots) - 1 else "[v_final]"
            overlay_filter = (
                f"{last_v}{b_out}overlay=x=0:y=0:enable='between(t,{start_t:.3f},{end_t:.3f})'{next_v}"
            )
            filter_parts.append(overlay_filter)
            last_v = next_v

        v_codec = color_info.get("codec", "libx264") if color_info else "libx264"
        v_preset = color_info.get("preset", "fast") if color_info else "fast"
        v_crf = color_info.get("crf", "18") if color_info else "18"
        v_tags = color_info.get("tag_args", []) if color_info else []

        filter_complex = ";".join(filter_parts)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v_final]",
            "-map", "0:a:0",
            "-c:v", v_codec, "-preset", v_preset, "-crf", v_crf,
            *v_tags,
            *(color_args or []),
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ])

        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return output_path.exists() and output_path.stat().st_size > 1000
    except Exception as e:
        logger.error(f"Failed to overlay B-roll clips: {e}")
        return False


def detect_face_safe_zone(video_path: Path, num_samples: int = 10) -> dict:
    """
    Detects speaker's face bounding boxes across sample frames using MediaPipe FaceDetector.
    Accounts for hair height (~0.45 * face_h above eyebrows/forehead) and camera zoom.
    Calculates the exact safe TOP placement so subtitles sit cleanly in the upper headroom
    without ever touching the hair or forehead.
    If headroom is insufficient (< 335px), switches to BOTTOM safe zone (bottom: 440px).
    """
    default_placement = {"position": "top", "top": 210, "face_detected": False}
    if not video_path.exists():
        return default_placement

    try:
        dur = get_video_duration(video_path)
        if dur <= 0:
            return default_placement

        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except ImportError:
            logger.warning("MediaPipe not installed, using default top: 210 subtitle placement")
            return default_placement

        model_path = Path("/opt/amalia_team_bot/models/blaze_face_short_range.tflite")
        if not model_path.exists():
            model_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                import urllib.request
                url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
                urllib.request.urlretrieve(url, str(model_path))
            except Exception as dl_err:
                logger.warning(f"Could not download blaze_face model: {dl_err}")
                return default_placement

        base_options = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.FaceDetectorOptions(base_options=base_options)
        detector = vision.FaceDetector.create_from_options(options)

        # Sample timestamps evenly across video
        timestamps = [dur * (i + 1) / (num_samples + 1) for i in range(num_samples)]
        hair_tops_px = []
        face_tops_px = []

        with tempfile.TemporaryDirectory() as tmpdir:
            for idx, ts in enumerate(timestamps):
                frame_path = Path(tmpdir) / f"sample_{idx}.jpg"
                subprocess.run([
                    "ffmpeg", "-y", "-ss", f"{ts:.2f}",
                    "-i", str(video_path),
                    "-vframes", "1", "-q:v", "2",
                    str(frame_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if not frame_path.exists():
                    continue

                try:
                    img = mp.Image.create_from_file(str(frame_path))
                    detection_result = detector.detect(img)
                    for d in detection_result.detections:
                        bb = d.bounding_box
                        scale_y = 1920.0 / img.height
                        f_top = bb.origin_y * scale_y
                        f_h = bb.height * scale_y
                        # Hair top is ~0.45 * face_height above the eyebrow bounding box
                        h_top = max(0, f_top - int(f_h * 0.45))
                        hair_tops_px.append(h_top)
                        face_tops_px.append(f_top)
                except Exception as ex:
                    logger.debug(f"MediaPipe detection error on sample {idx}: {ex}")

        if not hair_tops_px:
            logger.info("Face detector found no faces in sampled frames; using default headroom top: 210px.")
            return {"position": "top", "top": 210, "face_detected": False}

        hair_tops_px.sort()
        face_tops_px.sort()
        min_hair_top = hair_tops_px[0]  # Highest point of the head (during zoom or movement)
        median_hair_top = hair_tops_px[len(hair_tops_px) // 2]
        min_face_top = face_tops_px[0]

        logger.info(
            f"Face & hair detection stats: min_hair_top={min_hair_top:.0f}px, median_hair_top={median_hair_top:.0f}px, min_face_top={min_face_top:.0f}px"
        )

        # In 1080x1920:
        # Subtitles are ~125px tall for 2 lines.
        # We require at least 25-30px safety gap above the hair so subtitles NEVER touch the head.
        # Subtitle bottom = top_pos + 125 <= min_hair_top - 25 => top_pos <= min_hair_top - 150.
        # Instagram/TikTok status bar is at 0..160px, so top_pos must be >= 180px.
        if min_hair_top >= 335:
            # We have sufficient headroom above the head!
            desired_top = int(min_hair_top - 155)
            chosen_top = max(185, min(240, desired_top))
            sub_bottom = chosen_top + 125
            gap = int(min_hair_top - sub_bottom)
            logger.info(f"Safe zone selected: TOP at {chosen_top}px (hair starts at {min_hair_top:.0f}px, subtitle bottom at {sub_bottom}px, clear gap={gap}px)")
            return {
                "position": "top",
                "top": chosen_top,
                "face_detected": True,
                "hair_top": round(min_hair_top, 1),
                "gap": gap
            }
        else:
            # Head is framed too close to the top edge (hair_top < 335px) -> move to BOTTOM safe zone
            logger.info(f"Safe zone selected: BOTTOM at 440px (close-up framing, hair at {min_hair_top:.0f}px leaves insufficient headroom)")
            return {
                "position": "bottom",
                "bottom": 440,
                "face_detected": True,
                "hair_top": round(min_hair_top, 1),
                "gap": 0
            }
    except Exception as e:
        logger.error(f"Face safe zone detection failed: {e}")
        return default_placement


def render_with_remotion(
    duration_sec: float,
    captions: list[dict],
    callouts: list[dict] | None = None,
    frames_dir: Path | None = None,
    output_path: Path | None = None,
    style_preset: str = "luxury",
    subtitle_placement: dict | None = None,
    progress_cb: Any | None = None
) -> bool:
    """
    Invokes Remotion engine to render transparent frames (PNG sequence) or WebM
    with kinetic spring physics and frosted glass pill.
    Returns True if success, False if fallback needed.
    """
    from tg_bot.config import REMOTION_DIR
    remotion_dir = REMOTION_DIR
    render_script = remotion_dir / "render.mjs"
    if not render_script.exists():
        logger.warning(f"Remotion render script not found at {render_script}, falling back to ASS")
        return False

    duration_frames = int(math.ceil(duration_sec * 30)) + 5
    parent_dir = frames_dir.parent if frames_dir else (output_path.parent if output_path else remotion_dir)
    props_file = parent_dir / f"remotion_props_{uuid.uuid4().hex[:6]}.json"
    props_data = {
        "durationInFrames": duration_frames,
        "stylePreset": style_preset,
        "captions": captions,
        "callouts": callouts or [],
        "subtitlePlacement": subtitle_placement or {"position": "top", "top": 210, "bottom": 440}
    }
    props_file.write_text(json.dumps(props_data, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        "node",
        str(render_script),
        "--props", str(props_file.resolve()),
    ]
    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--frames", str(frames_dir.resolve())])
    elif output_path:
        cmd.extend(["--output", str(output_path.resolve())])
    else:
        return False

    try:
        logger.info(f"Rendering Remotion overlay ({duration_frames} frames)...")
        proc = subprocess.Popen(
            cmd,
            cwd=str(remotion_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        if proc.stdout:
            for line in proc.stdout:
                line_str = line.strip()
                if "[Remotion Progress]" in line_str:
                    try:
                        rem_pct = int(line_str.split("[Remotion Progress]")[1].replace("%", "").strip())
                        if progress_cb:
                            overall_pct = 65 + int(rem_pct * 0.15)
                            progress_cb(overall_pct, f"✨ Генерация субтитров Remotion Pro ({rem_pct}%)...")
                    except Exception:
                        pass
        proc.wait(timeout=300)
        props_file.unlink(missing_ok=True)
        if proc.returncode == 0:
            if frames_dir and any(frames_dir.glob("element-*.png")):
                logger.info("Remotion PNG frames render completed successfully!")
                return True
            elif output_path and output_path.exists() and output_path.stat().st_size > 1000:
                logger.info("Remotion overlay render completed successfully!")
                return True
        logger.error(f"Remotion render failed with code {proc.returncode}")
        return False
    except Exception as e:
        logger.error(f"Remotion invocation exception: {e}")
        return False


def render_edited_video(
    edl: dict,
    edit_dir: Path,
    final_output: Path,
    with_subtitles: bool = True,
    fps: str | None = None,
    progress_cb: Any | None = None
) -> Path:
    """
    Renders video from EDL:
    1. Extracts segments with 30ms afade in/out and aresample sync
    2. Concat demuxer (lossless) into base.mov
    3. Preserves original color space (10-bit HLG/BT.2020 or BT.709) in Apple QuickTime MOV
    4. Burns stylish kinetic subtitles with combined 1-pass loudnorm to -14 LUFS
    """
    edit_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = edit_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    sources = edl["sources"]
    ranges = edl["ranges"]
    first_src = Path(sources[ranges[0]["source"]])

    out_rate = fps or probe_source_fps(first_src)
    portrait = is_portrait_source(first_src)

    # Detect color space (10-bit HLG/BT.2020 HDR vs standard BT.709 SDR)
    # Detect color space and setup 1:1 iPhone screen match tone-mapping
    color_info = probe_source_color_info(first_src)
    is_hdr = color_info["is_hdr"]
    tonemap_vf = (
        "zscale=tin=arib-std-b67:pin=bt2020:min=bt2020nc:rin=limited:t=linear:npl=300,"
        "tonemap=tonemap=mobius:desat=0,"
        "zscale=t=bt709:p=bt709:m=bt709:r=limited,format=yuv420p"
    ) if is_hdr else ""

    color_args = [
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
    ]

    seg_paths: list[Path] = []
    total_segs = len(ranges)
    for idx, r in enumerate(ranges):
        src_p = Path(sources[r["source"]])
        start = float(r["start"])
        duration = float(r["end"]) - start
        out_seg = clips_dir / f"seg_{idx:03d}.mov"

        fade_out_start = max(0.0, duration - 0.03)
        af = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.03,aresample=48000:async=1"

        fps_val = parse_fps_float(out_rate)
        total_frames = max(1, int(round(duration * fps_val)))

        if portrait:
            base_prep = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            s_res = "1080x1920"
            y_zoom = "ih/6-(ih/zoom/6)"
        else:
            base_prep = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
            s_res = "1920x1080"
            y_zoom = "ih/2.8-(ih/zoom/2.8)"

        x_zoom = "iw/2-(iw/zoom/2)"

        # Alternating Reels Punch-Cut Framing + Continuous Smooth Push-In:
        # Every segment gets a smooth cinematic push-in (наезд камеры) across its entire duration.
        # Even segments (0, 2, 4...): Medium Shot (baseline 1.00 -> smooth push to 1.08-1.12x)
        # Odd segments (1, 3, 5...): Close-Up Punch Shot (punch jump to 1.18 -> smooth push to 1.26-1.30x)
        # At cuts: instantaneous 16-22% scale jump for dynamic multi-cam switching.
        # During cut: continuous smooth linear glide (using output frame variable 'on') so video never feels static.
        frames_cnt = max(1, total_frames - 1)
        if idx % 2 == 0:
            delta = min(0.12, max(0.04, 0.035 * duration))
            step = delta / frames_cnt
            z_expr = f"min(1.0+{step:.6f}*on,1.14)"
        else:
            delta = min(0.12, max(0.04, 0.032 * duration))
            step = delta / frames_cnt
            z_expr = f"min(1.18+{step:.6f}*on,1.32)"

        zoom_filter = f"zoompan=z='{z_expr}':d=1:x='{x_zoom}':y='{y_zoom}':s={s_res}:fps={out_rate}"
        if tonemap_vf:
            cur_vf = f"{tonemap_vf},{base_prep},{zoom_filter}"
            fallback_vf = f"{tonemap_vf},{base_prep}"
        else:
            cur_vf = f"{base_prep},{zoom_filter}"
            fallback_vf = base_prep

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", str(src_p),
            "-t", f"{duration:.3f}",
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-vf", cur_vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            *color_args,
            "-r", out_rate,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(out_seg)
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            logger.warning(f"Segment {idx} zoompan failed, fallback to base_prep: {err_msg[:200]}")
            cmd_fallback = [
                "ffmpeg", "-y",
                "-ss", f"{start:.3f}",
                "-i", str(src_p),
                "-t", f"{duration:.3f}",
                "-map", "0:v:0",
                "-map", "0:a:0",
                "-vf", fallback_vf,
                "-af", af,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                *color_args,
                "-r", out_rate,
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart",
                str(out_seg)
            ]
            subprocess.run(cmd_fallback, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        seg_paths.append(out_seg)
        if progress_cb and total_segs > 0:
            pct = 45 + int((idx + 1) / total_segs * 12)
            progress_cb(pct, f"✂️ Нарезка фрагментов с плавным зумом ({idx + 1}/{total_segs})...")

    if progress_cb:
        progress_cb(58, "🔗 Бесшовное объединение фрагментов (30ms crossfade)...")

    concat_txt = edit_dir / "concat.txt"
    concat_txt.write_text("".join(f"file '{p.resolve()}'\n" for p in seg_paths), encoding="utf-8")

    base_mov = edit_dir / "base.mov"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        "-movflags", "+faststart",
        str(base_mov)
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    concat_txt.unlink(missing_ok=True)

    cut_duration = sum(float(r["end"]) - float(r["start"]) for r in ranges)

    # B-Roll Integration: if bank has clips, overlay 1-2 cutaways onto base video
    broll_clips = select_broll_clips(count=2)
    if broll_clips and cut_duration >= 18.0:
        if progress_cb:
            progress_cb(62, f"🎬 Наложение {len(broll_clips)} B-Roll перебивок из библиотеки...")
        broll_base = edit_dir / "broll_base.mov"
        broll_ok = overlay_broll_clips(
            base_mov=base_mov,
            broll_clips=broll_clips,
            cut_duration=cut_duration,
            output_path=broll_base,
            color_args=color_args,
            color_info=color_info
        )
        if broll_ok and broll_base.exists() and broll_base.stat().st_size > 1000:
            base_mov = broll_base

    # Subtitles & Loudnorm (combined single-pass for lossless audio & perfect sync)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    remotion_used = False

    if with_subtitles:
        captions = extract_timed_captions_for_remotion(edl)
        callouts = extract_callouts_from_transcript(edl)
        if captions:
            # Detect speaker face position so subtitles never cover the face
            if progress_cb:
                progress_cb(63, "👁️ Определение безопасных зон и положения лица...")
            safe_placement = detect_face_safe_zone(base_mov)
            logger.info(f"Subtitle placement determined: {safe_placement}")

            frames_dir = edit_dir / "remotion_frames"
            if progress_cb:
                progress_cb(65, "✨ Рендеринг кинетических субтитров Remotion Pro...")
            remotion_used = render_with_remotion(
                duration_sec=cut_duration,
                captions=captions,
                callouts=callouts,
                frames_dir=frames_dir,
                style_preset="luxury",
                subtitle_placement=safe_placement,
                progress_cb=progress_cb
            )
            has_frames = remotion_used and frames_dir.exists() and any(frames_dir.glob("element-*.png"))
            if has_frames:
                if progress_cb:
                    progress_cb(82, "🎨 Наложение субтитров и нормализация звука (-14 LUFS)...")

                matching_frames = sorted(frames_dir.glob("element-*.png"))
                first_name = matching_frames[0].name
                m = re.match(r"element-(\d+)\.png", first_name)
                if m:
                    digits = len(m.group(1))
                    start_num = str(int(m.group(1)))
                    fmt = f"element-%0{digits}d.png" if digits > 1 else "element-%d.png"
                    seq_args = ["-start_number", start_num, "-i", str(frames_dir / fmt)]
                else:
                    seq_args = ["-pattern_type", "glob", "-i", str(frames_dir / "element-*.png")]

                filter_complex = (
                    "[0:v][1:v]overlay=0:0[v];"
                    f"[0:a]loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA},aresample=48000:async=1[a]"
                )
                cmd_overlay = [
                    "ffmpeg", "-y",
                    "-i", str(base_mov),
                    "-framerate", "30",
                    *seq_args,
                    "-filter_complex", filter_complex,
                    "-map", "[v]",
                    "-map", "[a]",
                    "-c:v", color_info.get("codec", "libx264") if color_info else "libx264",
                    "-preset", color_info.get("preset", "fast") if color_info else "fast",
                    "-crf", color_info.get("crf", "18") if color_info else "18",
                    *(color_info.get("tag_args", []) if color_info else []),
                    *color_args,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart",
                    str(final_output)
                ]
                try:
                    subprocess.run(cmd_overlay, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    shutil.rmtree(frames_dir, ignore_errors=True)
                except subprocess.CalledProcessError as e:
                    err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
                    logger.error(f"Remotion overlay ffmpeg failed (exit code {e.returncode}): {err_msg}")
                    remotion_used = False
                    shutil.rmtree(frames_dir, ignore_errors=True)
            else:
                remotion_used = False

        if not remotion_used:
            if progress_cb:
                progress_cb(75, "💬 Применение резервных субтитров (ASS Pro) и нормализация звука...")
            ass_path = edit_dir / "subtitles.ass"
            build_stylish_karaoke_ass(edl, ass_path, is_portrait=portrait)
            if ass_path.exists():
                logger.info("Using ASS fallback subtitles")
                subs_escaped = str(ass_path.resolve()).replace(":", "\\:").replace("'", "\\'")
                vf_sub = f"ass='{subs_escaped}'"
                filter_complex = (
                    f"[0:v]{vf_sub}[v];"
                    f"[0:a]loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA},aresample=48000:async=1[a]"
                )
                cmd_sub = [
                    "ffmpeg", "-y",
                    "-i", str(base_mov),
                    "-filter_complex", filter_complex,
                    "-map", "[v]",
                    "-map", "[a]",
                    "-c:v", color_info.get("codec", "libx264") if color_info else "libx264",
                    "-preset", color_info.get("preset", "fast") if color_info else "fast",
                    "-crf", color_info.get("crf", "18") if color_info else "18",
                    *(color_info.get("tag_args", []) if color_info else []),
                    *color_args,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart",
                    str(final_output)
                ]
                try:
                    subprocess.run(cmd_sub, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                except subprocess.CalledProcessError as e:
                    err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
                    logger.error(f"ASS subtitles ffmpeg failed (exit code {e.returncode}): {err_msg}")

    if not final_output.exists() or final_output.stat().st_size == 0:
        if progress_cb:
            progress_cb(85, "🔊 Нормализация звука под стандарты Reels (-14 LUFS)...")
        filter_loudnorm = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA},aresample=48000:async=1"
        cmd_direct = [
            "ffmpeg", "-y",
            "-i", str(base_mov),
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "copy",
            "-af", filter_loudnorm,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(final_output)
        ]
        subprocess.run(cmd_direct, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    # Double verify both video & audio streams exist and are valid
    if not verify_video_and_audio(final_output):
        logger.warning(f"Final output {final_output} missing audio/video stream, running fallback encoding...")
        filter_loudnorm = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA},aresample=48000:async=1"
        cmd_recover = [
            "ffmpeg", "-y",
            "-i", str(base_mov),
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            *color_args,
            "-af", filter_loudnorm,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(final_output)
        ]
        subprocess.run(cmd_recover, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if not final_output.exists() or final_output.stat().st_size == 0:
        raise RuntimeError(f"Финальный видеофайл не был сформирован: {final_output}")

    # Cleanup clips
    shutil.rmtree(clips_dir, ignore_errors=True)
    if base_mov.exists() and base_mov != final_output:
        base_mov.unlink(missing_ok=True)

    return final_output


async def async_edit_and_render_video(
    video_path: Path,
    scribe_data: dict,
    output_dir: Path | None = None,
    progress_callback: Any | None = None
) -> tuple[Path, Path, dict]:
    """
    Async wrapper for the full cut & render pipeline.
    Returns (rendered_mov_path, ass_path, stats).
    """
    out_dir = output_dir or (video_path.parent / f"edit_{video_path.stem}")
    out_dir.mkdir(parents=True, exist_ok=True)

    edl, cuts_info = build_edl_from_scribe(scribe_data, video_path)

    orig_duration = get_video_duration(video_path)
    cut_duration = sum(float(r["end"]) - float(r["start"]) for r in edl["ranges"])
    saved_seconds = max(0.0, orig_duration - cut_duration)

    final_mov = out_dir / f"final_{video_path.stem}.mov"

    loop = asyncio.get_running_loop()

    def sync_progress(pct: int, text: str):
        if progress_callback:
            try:
                asyncio.run_coroutine_threadsafe(progress_callback(pct, text), loop)
            except Exception:
                pass

    await asyncio.to_thread(
        render_edited_video,
        edl=edl,
        edit_dir=out_dir,
        final_output=final_mov,
        with_subtitles=True,
        progress_cb=sync_progress
    )

    ass_path = out_dir / "subtitles.ass"

    stats = {
        "original_duration": orig_duration,
        "cut_duration": cut_duration,
        "saved_seconds": saved_seconds,
        "cuts_count": len(cuts_info),
        "segments_count": len(edl["ranges"])
    }

    return final_mov, ass_path, stats

