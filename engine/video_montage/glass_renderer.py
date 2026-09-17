import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from .config import (
    TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS,
    GLASS_PALETTES, INACTIVE_COLOR, STROKE_COLOR, FONTS_DIR
)

FONT_PATH = FONTS_DIR / "Montserrat.ttf"

def get_font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    """Loads Montserrat with specific variation weight (Black / ExtraBold / Bold)."""
    if FONT_PATH.exists():
        try:
            f = ImageFont.truetype(str(FONT_PATH), size)
            f.set_variation_by_name(weight)
            return f
        except Exception:
            pass
    # Fallback to system font
    sys_path = "/System/Library/Fonts/Supplemental/Arial Black.ttf" if weight == "Black" else "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    if os.path.exists(sys_path):
        try:
            return ImageFont.truetype(sys_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


class GlassSubtitleRenderer:
    """Renders high-retention Brandly kinetic subtitles."""

    def __init__(self, palette_name: str = "amber", show_hook: bool = True, watermark_text: Optional[str] = "Brandly AI"):
        self.palette = GLASS_PALETTES.get(palette_name, GLASS_PALETTES["amber"])
        self.active_color = self.palette["active_color"]
        self.show_hook = show_hook
        self.watermark_text = watermark_text

        # Base Fonts
        self.font_context = get_font(52, "Bold")
        self.font_active_base = get_font(108, "Black")
        self.font_hook = get_font(42, "ExtraBold")
        self.font_watermark = get_font(30, "Bold")

    def group_words_into_phrases(self, words: List[Dict[str, Any]], max_words_per_phrase: int = 5, max_duration: float = 2.4) -> List[List[Dict[str, Any]]]:
        """Groups words into natural rhythmic sentence chunks for kinetic display."""
        phrases = []
        current = []

        for w in words:
            if not current:
                current.append(w)
                continue

            chunk_duration = w["end"] - current[0]["start"]
            ends_with_punct = current[-1]["word"].rstrip().endswith((".", "!", "?"))

            if len(current) >= max_words_per_phrase or chunk_duration > max_duration or ends_with_punct:
                phrases.append(current)
                current = [w]
            else:
                current.append(w)

        if current:
            phrases.append(current)

        return phrases

    def get_state_key(self, time_sec: float, phrases: List[List[Dict[str, Any]]], hook_text: Optional[str] = None) -> Tuple[int, int, bool]:
        """Returns a discrete state key for frame memoization."""
        show_hook = bool(self.show_hook and hook_text and time_sec <= 3.2)
        active_p_idx = -1
        active_w_idx = -1

        for p_idx, phrase in enumerate(phrases):
            p_start = phrase[0]["start"]
            p_end = phrase[-1]["end"]
            if p_start <= time_sec <= p_end + 0.2:
                active_p_idx = p_idx
                for w_idx, w in enumerate(phrase):
                    if w["start"] <= time_sec <= w["end"] + 0.12:
                        active_w_idx = w_idx
                        break
                if active_w_idx == -1 and phrase:
                    active_w_idx = min(range(len(phrase)), key=lambda i: abs(phrase[i]["start"] - time_sec))
                break

        return (active_p_idx, active_w_idx, show_hook)

    def render_frame(self, time_sec: float, phrases: List[List[Dict[str, Any]]], hook_text: Optional[str] = None) -> Image.Image:
        """Renders transparent RGBA overlay frame with 3-tier Brandly kinetic typography."""
        frame = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # 1. Top Hook Card (first 3.2 seconds)
        if self.show_hook and hook_text and time_sec <= 3.2:
            self._draw_hook_card(draw, hook_text, time_sec)

        # 2. Watermark
        if self.watermark_text:
            self._draw_watermark(draw, self.watermark_text)

        # 3. Find active phrase and active word
        active_phrase = None
        active_word_idx = -1

        for phrase in phrases:
            p_start = phrase[0]["start"]
            p_end = phrase[-1]["end"]
            if p_start <= time_sec <= p_end + 0.2:
                active_phrase = phrase
                for idx, w in enumerate(phrase):
                    if w["start"] <= time_sec <= w["end"] + 0.12:
                        active_word_idx = idx
                        break
                if active_word_idx == -1 and phrase:
                    active_word_idx = min(range(len(phrase)), key=lambda i: abs(phrase[i]["start"] - time_sec))
                break

        if not active_phrase or active_word_idx == -1:
            return frame

        # 4. Render 3-Tier Kinetic Typography
        self._draw_kinetic_typography(draw, active_phrase, active_word_idx)
        return frame

    def _draw_hook_card(self, draw: ImageDraw.Draw, hook_text: str, time_sec: float):
        """Draws sleek top hook banner in the upper third with crisp vector lightning bolt."""
        text = hook_text.upper()
        bbox = self.font_hook.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        icon_size = 32
        icon_gap = 12
        pad_x, pad_y = 32, 16

        content_w = icon_size + icon_gap + text_w
        box_w = content_w + pad_x * 2
        box_h = max(text_h, icon_size) + pad_y * 2
        center_x = TARGET_WIDTH // 2
        center_y = 360

        x0 = center_x - box_w // 2
        y0 = center_y - box_h // 2
        x1 = x0 + box_w
        y1 = y0 + box_h

        # Modern glass pill with accent border
        draw.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=(12, 10, 18, 215), outline=self.active_color, width=3)

        # Vector lightning bolt
        icon_x = x0 + pad_x
        icon_y = center_y - icon_size // 2
        bolt_pts = [
            (icon_x + 0.62 * icon_size, icon_y),
            (icon_x + 0.12 * icon_size, icon_y + 0.55 * icon_size),
            (icon_x + 0.48 * icon_size, icon_y + 0.55 * icon_size),
            (icon_x + 0.35 * icon_size, icon_y + 1.0 * icon_size),
            (icon_x + 0.90 * icon_size, icon_y + 0.42 * icon_size),
            (icon_x + 0.52 * icon_size, icon_y + 0.42 * icon_size)
        ]
        draw.polygon(bolt_pts, fill=self.active_color)

        # Text with shadow
        tx = icon_x + icon_size + icon_gap
        ty = center_y - text_h // 2 - 3
        draw.text((tx + 2, ty + 2), text, font=self.font_hook, fill=(0, 0, 0, 220))
        draw.text((tx, ty), text, font=self.font_hook, fill=(255, 255, 255, 255))

    def _draw_watermark(self, draw: ImageDraw.Draw, text: str):
        """Draws watermark in top right corner."""
        bbox = self.font_watermark.getbbox(text)
        w = bbox[2] - bbox[0]
        x = TARGET_WIDTH - w - 50
        y = 100
        draw.text((x + 2, y + 2), text, font=self.font_watermark, fill=(0, 0, 0, 180))
        draw.text((x, y), text, font=self.font_watermark, fill=(255, 255, 255, 140))

    def _draw_text_with_deep_shadow(self, draw: ImageDraw.Draw, pos: Tuple[int, int], text: str, font: ImageFont.FreeTypeFont, fill: Any, stroke_w: int = 4):
        """Draws high-contrast text with multi-layer shadow and dark stroke for legibility over video."""
        x, y = pos
        # Deep shadow layers
        for dx, dy in [(3, 3), (4, 4), (-2, 2), (2, -2), (0, 4)]:
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 190))
        # Stroke + fill
        draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=(12, 10, 18, 255))

    def _draw_kinetic_typography(self, draw: ImageDraw.Draw, phrase: List[Dict[str, Any]], active_idx: int):
        """Renders 3-tier Brandly kinetic layout: top context, massive active word, bottom context."""
        active_item = phrase[active_idx]
        active_word = active_item["word"].upper()
        if "emoji" in active_item:
            active_word = f"{active_item['emoji']} {active_word}"

        # Group preceding and succeeding words
        prev_words = [item["word"] for item in phrase[:active_idx]]
        next_words = [item["word"] for item in phrase[active_idx + 1:]]

        top_text = "   ".join(prev_words).lower() if prev_words else ""
        bottom_text = "   ".join(next_words).lower() if next_words else ""

        # Measure active word & autoscale if too wide
        max_allowed_w = TARGET_WIDTH - 140
        font_size = 106

        font_active = get_font(font_size, "Black")
        bbox = font_active.getbbox(active_word)
        w = bbox[2] - bbox[0]

        if w > max_allowed_w:
            scale = max_allowed_w / max(w, 1)
            font_size = max(64, int(font_size * scale))
            font_active = get_font(font_size, "Black")
            bbox = font_active.getbbox(active_word)
            w = bbox[2] - bbox[0]

        h = bbox[3] - bbox[1]

        center_x = TARGET_WIDTH // 2
        center_y = 1180  # Chest area of the speaker

        active_x = center_x - w // 2
        active_y = center_y - h // 2

        # 1. Top Context Text
        if top_text:
            top_bbox = self.font_context.getbbox(top_text)
            top_w = top_bbox[2] - top_bbox[0]
            top_x = center_x - top_w // 2
            top_y = active_y - 66
            self._draw_text_with_deep_shadow(draw, (top_x, top_y), top_text, self.font_context, fill=(255, 255, 255, 255), stroke_w=3)

        # 2. Massive Active Word (Center)
        self._draw_text_with_deep_shadow(draw, (active_x, active_y), active_word, font_active, fill=self.active_color, stroke_w=6)

        # 3. Bottom Context Text
        if bottom_text:
            bot_bbox = self.font_context.getbbox(bottom_text)
            bot_w = bot_bbox[2] - bot_bbox[0]
            bot_x = center_x - bot_w // 2
            bot_y = active_y + h + 16
            self._draw_text_with_deep_shadow(draw, (bot_x, bot_y), bottom_text, self.font_context, fill=(255, 255, 255, 255), stroke_w=3)
