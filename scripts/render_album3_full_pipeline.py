#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / ".agents/skills/music-channel/scripts"))

# Ensure environment
os.environ["ALBUM_NAME"] = "album-3"
import common
from visualizer_engine import render_visualizer_video

ALBUM_DIR = REPO / "project-assets" / "album-3"
PROJECTS_DIR = REPO / "projects" / "album-3"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
MASTERS_MANIFEST = PROJECTS_DIR / "audio-masters" / "artifacts" / "masters.json"

def main():
    if not MASTERS_MANIFEST.exists():
        print(f"Masters manifest not found at {MASTERS_MANIFEST}")
        return

    data = json.loads(MASTERS_MANIFEST.read_text(encoding="utf-8"))
    tracks = data["tracks"]
    print(f"Total tracks to render for Album 3: {len(tracks)}")

    # Pools of clips for character overlay
    branding_clips = list((REPO / "project-assets" / "channel-branding" / "videos").glob("*.mp4"))

    for idx, track in enumerate(tracks, 1):
        slug = track["slug"]
        title = track["title"]
        master_audio = Path(track["master"])

        # Project folder
        project = PROJECTS_DIR / f"single-{slug}"
        renders_dir = project / "renders"
        artifacts_dir = project / "artifacts"
        images_dir = project / "assets" / "images"
        renders_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        (artifacts_dir / "title.txt").write_text(title, encoding="utf-8")
        (artifacts_dir / "subtitle.txt").write_text("Funky Destiny", encoding="utf-8")

        out_video = renders_dir / f"{slug}.mp4"
        thumb_out = renders_dir / f"{slug}-thumb.jpg"

        # Find artwork
        clean_art = None
        for track_dir in ALBUM_DIR.iterdir():
            if track_dir.is_dir() and slug in track_dir.name.lower().replace(" ", "-"):
                imgs = [f for f in track_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
                if imgs:
                    clean_art = imgs[0]
                    break
        if clean_art is None:
            clean_art = REPO / "project-assets" / "channel-branding" / "thumb_clean_base.jpg"

        # Generate clean thumbnail (raw art + HUD badge)
        if not thumb_out.exists():
            try:
                from PIL import Image
                hud_path = REPO / "project-assets" / "channel-branding" / "hud_badge_opaque_tight.png"
                bg = Image.open(clean_art).convert("RGB")
                thumb = bg.resize((1280, 720), getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.ANTIALIAS)).convert("RGBA")
                if hud_path.exists():
                    hud = Image.open(hud_path).convert("RGBA")
                    hud_w = int(1280 * 0.22)
                    hud_h = int(hud_w * hud.height / hud.width)
                    hud_scaled = hud.resize((hud_w, hud_h), getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.ANTIALIAS))
                    pos_x = 1280 - hud_w - 32
                    pos_y = 720 - hud_h - 32
                    thumb.paste(hud_scaled, (pos_x, pos_y), hud_scaled)
                thumb.convert("RGB").save(thumb_out, "JPEG", quality=95)
            except Exception as e:
                print(f"  Warning creating thumbnail: {e}")

        # Check if video exists
        if out_video.exists() and out_video.stat().st_size > 1000000:
            print(f"[{idx}/{len(tracks)}] Already rendered: {title} ({out_video})")
            continue

        print(f"\n[{idx}/{len(tracks)}] Rendering Visualizer: {title}")
        print(f"  Audio: {master_audio.name}")
        print(f"  Art:   {clean_art.name}")

        # Gather character clips: track-specific mp4 if present + shuffled channel branding clips
        char_clips = []
        for track_dir in ALBUM_DIR.iterdir():
            if track_dir.is_dir() and slug in track_dir.name.lower().replace(" ", "-"):
                mp4s = [f for f in track_dir.glob("*.mp4")]
                if mp4s:
                    char_clips.extend(mp4s)
        
        import random
        shuffled_branding = list(branding_clips)
        random.shuffle(shuffled_branding)
        char_clips.extend(shuffled_branding)

        render_visualizer_video(
            audio_path=master_audio,
            clean_art_path=clean_art,
            output_path=out_video,
            char_clips=char_clips,
            fps=30,
            crf=18,
            preset="veryfast"
        )
        print(f"  ✅ Rendered successfully: {out_video}")

    print("\n🎉 All 12 Full Music Videos rendered successfully for Album 3!")

if __name__ == "__main__":
    main()
