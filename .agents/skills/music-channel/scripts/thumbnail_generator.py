"""Thumbnail generation module for YouTube music channel.

Generates 1280x720 high-CTR thumbnails:
- Left: The Judge hero in action with bass guitar
- Right: Song / Mix title in bold cyberpunk typography with neon glow
- Badge: Channel name ('FUNKY DESTINY') and genre / duration tags
"""
from __future__ import annotations

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# Find best bold sans font on system
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/selawik-zorin-os/selawkb.ttf",
]


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()


def get_text_dimensions(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    elif hasattr(draw, "textsize"):
        return draw.textsize(text, font=font)
    elif hasattr(font, "getsize"):
        return font.getsize(text)
    return len(text) * 10, 20


DEFAULT_BASE_ART = Path(__file__).resolve().parent.parent.parent.parent.parent / "project-assets" / "channel-branding" / "thumb_clean_base.jpg"
HUD_BADGE_PNG = Path(__file__).resolve().parent.parent.parent.parent.parent / "project-assets" / "channel-branding" / "hud_badge_right.png"


def create_thumbnail(
    title: str,
    output_path: Path,
    subtitle: str = "FUNKY DESTINY",
    badge_text: str = "HEAVY BASS GROOVE",
    base_art: Path | None = None,
    color_accent: tuple[int, int, int] = (255, 30, 66),  # Crimson Red
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if base_art is None and DEFAULT_BASE_ART.exists():
        base_art = DEFAULT_BASE_ART

    w, h = 1280, 720
    # 1. Base art / background
    resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.ANTIALIAS)
    if base_art and Path(base_art).exists():
        bg = Image.open(base_art).convert("RGB")
        bg = bg.resize((w, h), resample_filter)
    else:
        # Fallback dark industrial background
        bg = Image.new("RGB", (w, h), (11, 12, 16))

    # Add dark vignette / gradient on the right side to guarantee text contrast
    gradient = Image.new("L", (w, h), 0)
    gdraw = ImageDraw.Draw(gradient)
    # Right 58% of the screen gets darker
    for x in range(int(w * 0.42), w):
        alpha = int(((x - (w * 0.42)) / (w * 0.58)) * 210)
        gdraw.line([(x, 0), (x, h)], fill=alpha)
    
    dark_overlay = Image.new("RGBA", (w, h), (5, 6, 8, 255))
    dark_overlay.putalpha(gradient)
    
    img = bg.convert("RGBA")
    img.alpha_composite(dark_overlay)

    # 2. Typography
    draw = ImageDraw.Draw(img)

    # Maximum allowed width for title (from text_x to right margin)
    text_x = int(w * 0.47)
    max_title_w = w - text_x - 50
    max_title_h = 240

    # Fit title font size dynamically
    font_size = 90
    words = title.upper().split()
    
    while font_size >= 40:
        test_font = get_font(font_size)
        lines = []
        curr = []
        for word in words:
            cand = " ".join(curr + [word])
            cw, _ = get_text_dimensions(draw, cand, test_font)
            if cw > max_title_w and curr:
                lines.append(" ".join(curr))
                curr = [word]
            else:
                curr.append(word)
        if curr:
            lines.append(" ".join(curr))
            
        line_spacing = int(font_size * 1.14)
        total_h = len(lines) * line_spacing
        
        fits = True
        for l in lines:
            lw, _ = get_text_dimensions(draw, l, test_font)
            if lw > max_title_w:
                fits = False
                break
        if fits and total_h <= max_title_h:
            break
        font_size -= 4

    title_font = get_font(font_size)
    badge_font = get_font(24)

    line_spacing = int(font_size * 1.14)
    start_y = 85

    # Draw Title with 3D shadow and Neon Glow
    for i, line in enumerate(lines):
        y = start_y + (i * line_spacing)
        
        # Deep shadow
        for off in [(6, 6), (5, 5), (4, 4), (3, 3), (2, 2)]:
            draw.text((text_x + off[0], y + off[1]), line, font=title_font, fill=(0, 0, 0, 240))
        
        # Neon edge glow
        for off in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)]:
            draw.text((text_x + off[0], y + off[1]), line, font=title_font, fill=color_accent + (180,))

        # Core bright white fill
        draw.text((text_x, y), line, font=title_font, fill=(255, 255, 255, 255))

    # Genre / Tag Pill
    tag_y = start_y + (len(lines) * line_spacing) + 24
    bw, bh = get_text_dimensions(draw, badge_text, badge_font)
    badge_box = [text_x - 16, tag_y - 8, text_x + bw + 16, tag_y + bh + 8]
    draw.rectangle(badge_box, fill=(18, 20, 26, 240), outline=color_accent, width=2)
    draw.text((text_x, tag_y - 2), badge_text, font=badge_font, fill=(255, 220, 80, 255))

    # 3. Outer border frame
    border_color = color_accent + (200,)
    draw.rectangle([10, 10, w - 10, h - 10], outline=(15, 17, 22, 220), width=6)
    draw.rectangle([14, 14, w - 14, h - 14], outline=border_color, width=2)

    # 4. HUD Official Seal / Badge in bottom right
    if HUD_BADGE_PNG.exists():
        badge_raw = Image.open(HUD_BADGE_PNG)
        bbox = badge_raw.getbbox()
        badge_tight = badge_raw.crop(bbox) if bbox else badge_raw
        
        target_w = 410
        target_h = int(badge_tight.height * (target_w / badge_tight.width))
        badge_scaled = badge_tight.resize((target_w, target_h), resample_filter)
        
        badge_x = w - target_w - 30
        badge_y = h - target_h - 26
        img.paste(badge_scaled, (badge_x, badge_y), badge_scaled)

    # Save finalized JPG
    final = img.convert("RGB")
    final.save(output_path, "JPEG", quality=95)
    print(f"[thumbnail] Saved: {output_path}")
    return output_path

