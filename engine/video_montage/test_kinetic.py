from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = Path(__file__).resolve().parent / "fonts" / "Montserrat.ttf"

def get_montserrat(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    try:
        font.set_variation_by_name(weight)
    except Exception:
        pass
    return font

def draw_kinetic_subtitles(
    base_img: Image.Image,
    top_text: str,
    active_text: str,
    bottom_text: str,
    active_color: tuple = (255, 230, 0, 255),
    center_y: int = 1180
) -> Image.Image:
    """Draws 3-tier Brandly-style kinetic subtitles over the image."""
    img = base_img.copy().convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    font_context = get_montserrat(56, "Bold")
    font_active = get_montserrat(124, "Black")

    def draw_text_with_shadow(draw, pos, text, font, fill, stroke_w=5):
        x, y = pos
        # Rich layered drop shadow
        for dx, dy in [(4, 4), (5, 5), (-3, 3), (3, -3), (0, 5)]:
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 180))
        # Deep contrast stroke + fill
        draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=(12, 10, 18, 255))

    # 1. Active Word (Center)
    active_bbox = font_active.getbbox(active_text)
    active_w = active_bbox[2] - active_bbox[0]
    active_h = active_bbox[3] - active_bbox[1]
    active_x = (w - active_w) // 2
    active_y = center_y - active_h // 2

    # 2. Top Text
    if top_text:
        top_bbox = font_context.getbbox(top_text)
        top_w = top_bbox[2] - top_bbox[0]
        top_x = (w - top_w) // 2
        top_y = active_y - 72
        draw_text_with_shadow(draw, (top_x, top_y), top_text, font_context, fill=(255, 255, 255, 255), stroke_w=3)

    # Draw Center Word (Active highlighted)
    draw_text_with_shadow(draw, (active_x, active_y), active_text, font_active, fill=active_color, stroke_w=6)

    # 3. Bottom Text
    if bottom_text:
        bottom_bbox = font_context.getbbox(bottom_text)
        bottom_w = bottom_bbox[2] - bottom_bbox[0]
        bottom_x = (w - bottom_w) // 2
        bottom_y = active_y + active_h + 18
        draw_text_with_shadow(draw, (bottom_x, bottom_y), bottom_text, font_context, fill=(255, 255, 255, 255), stroke_w=3)

    return img

if __name__ == "__main__":
    speaker_img = Image.open("engine/video_montage/sample_speaker.jpg")
    out = draw_kinetic_subtitles(
        speaker_img,
        top_text="это     пример",
        active_text="СУБТИТРОВ",
        bottom_text="в стиле     Glass",
        active_color=(255, 230, 0, 255),
        center_y=1180
    )
    out.save("/Users/a123456/.gemini/antigravity-ide/brain/20e939b4-f49a-451c-a02e-4406316ad41a/test_kinetic_frame.png")
    print("Saved test_kinetic_frame.png successfully!")
