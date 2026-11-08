#!/usr/bin/env python3
"""Render single songs synchronized to rhythmic beats and instrument cues.

Features:
- Dynamic audio-reactive LED equalizer on bottom-left (Green -> Yellow -> Orange -> Red).
- Official Neopunk HUD badge on bottom-right (tactical metallic frame, avatar, glowing title).
- Unique per-song visual personality:
  * Color grading / atmosphere tinting based on musical genre tag (@heavybass, @guitarboy, @smoothbass, etc.)
  * Custom pacing: cuts adapt to BPM and song character
  * Tailored instrument focus per song style
"""
from __future__ import annotations

import argparse
import json
import math
import random
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CHANNEL_NAME, PROJECTS, REPO, VIDEOS_DIR, blur_pad_filter, find_font,  # noqa: E402
                    load_masters, probe_duration, require_ffmpeg, resolve_master, run)
from thumbnail_generator import create_thumbnail

HUD_BADGE_PNG = REPO / "project-assets" / "channel-branding" / "hud_badge_right.png"
GRID_MASK_PNG = REPO / "project-assets" / "channel-branding" / "eq_grid_mask.png"

# Color grading profiles by tag / personality
THEMES = {
    "heavybass": {
        # High contrast, deep crimson shadow, electric amber highlights
        "eq_f": 380,
        "bars_cut": 2,
        "color_adjust": "eq=contrast=1.12:brightness=-0.02:saturation=1.15,colorbalance=rs=0.12:gs=-0.02:bs=-0.08:rh=0.08:bh=-0.06",
        "role_weights": ["bass", "bass", "drums", "bass", "reaction"],
    },
    "guitarboy": {
        # Warm golden-amber wash, vibrant electric tones
        "eq_f": 450,
        "bars_cut": 2,
        "color_adjust": "eq=contrast=1.08:brightness=0.0:saturation=1.2,colorbalance=rs=0.08:gs=0.02:bs=-0.08:rm=0.06:gm=0.02:bm=-0.04",
        "role_weights": ["guitar", "bass", "guitar", "drums", "reaction"],
    },
    "smoothbass": {
        # Cyberpunk neon cyan / violet night atmosphere
        "eq_f": 350,
        "bars_cut": 4,
        "color_adjust": "eq=contrast=1.05:brightness=-0.01:saturation=1.1,colorbalance=rs=-0.05:gs=0.02:bs=0.1:rh=-0.04:gh=0.02:bh=0.08",
        "role_weights": ["bass", "reaction", "bass", "reaction", "drums"],
    },
    "pianobass": {
        # Elegant moody dark studio grading
        "eq_f": 400,
        "bars_cut": 3,
        "color_adjust": "eq=contrast=1.06:brightness=-0.02:saturation=1.05,colorbalance=rs=0.04:gs=0.02:bs=0.02",
        "role_weights": ["reaction", "bass", "drums", "reaction", "bass"],
    },
    "mediumbass": {
        # Acid energetic funk grading
        "eq_f": 420,
        "bars_cut": 2,
        "color_adjust": "eq=contrast=1.1:brightness=-0.01:saturation=1.22,colorbalance=rs=0.06:gs=0.04:bs=-0.05",
        "role_weights": ["bass", "drums", "reaction", "bass", "guitar"],
    },
}

DEFAULT_THEME = THEMES["mediumbass"]


def detect_tempo_and_beats(audio_path: Path) -> tuple[float, float]:
    """Detect BPM and major rhythmic bar changes from audio low-end."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(audio_path),
        "-af", "lowpass=f=200,highpass=f=40",
        "-ac", "1", "-ar", "22050", "-f", "s16le", "-"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    raw, _ = proc.communicate()
    samples = [struct.unpack("<h", raw[i:i+2])[0] for i in range(0, len(raw), 2)]
    
    frame_size = int(22050 * 0.05)
    energies = []
    for i in range(0, len(samples) - frame_size, frame_size):
        chunk = samples[i:i+frame_size]
        rms = math.sqrt(sum(s*s for s in chunk)/len(chunk))
        energies.append(rms)

    peaks = []
    for i in range(1, len(energies)-1):
        if energies[i] > 1400 and energies[i] > energies[i-1] and energies[i] > energies[i+1]:
            peaks.append(i * 0.05)

    diffs = [peaks[i]-peaks[i-1] for i in range(1, len(peaks))]
    valid_diffs = [d for d in diffs if 0.3 <= d <= 0.8]
    if valid_diffs:
        beat_interval = sum(valid_diffs) / len(valid_diffs)
        bpm = 60.0 / beat_interval
    else:
        bpm = 125.0
        beat_interval = 0.48

    bar_length = beat_interval * 4
    return bpm, bar_length


def categorize_clips() -> dict[str, list[Path]]:
    clips = sorted(VIDEOS_DIR.glob("*.mp4"))
    return {
        "bass": [c for c in clips if "baixo" in c.stem.lower()],
        "drums": [c for c in clips if "drum" in c.stem.lower()],
        "guitar": [c for c in clips if "guitar" in c.stem.lower()],
        "reaction": [c for c in clips if "enjoying" in c.stem.lower()],
    }


def render_single_song(song_slug: str, force: bool = False, crf: int = 18, preset: str = "medium") -> Path:
    require_ffmpeg()
    track = resolve_master(song_slug)
    master = Path(track["master"])
    dur = probe_duration(master)
    w, h, fps = 1920, 1080, 30

    project = PROJECTS / f"single-{track['slug']}"
    (project / "renders").mkdir(parents=True, exist_ok=True)
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "video").mkdir(parents=True, exist_ok=True)

    out = project / "renders" / f"{track['slug']}.mp4"
    thumb_out = project / "renders" / f"{track['slug']}-thumb.jpg"
    tag = (track.get("tag") or "").lower()
    badge_label = f"{tag.upper()} // BASS" if tag else "HEAVY BASS GROOVE"

    slug = track["slug"]

    # Clean AI Artwork path resolution:
    # 1) Specific artwork inside project-assets/album-2/<track_dir>/
    # 2) Specific raw artwork in projects/<album>/single-<slug>/assets/images/
    # 3) Fallback to thumbnail base art or default
    clean_art = None
    album_dir = REPO / "project-assets" / "album-2"
    if album_dir.exists():
        for track_dir in album_dir.iterdir():
            if track_dir.is_dir() and slug in track_dir.name.lower().replace(" ", "-"):
                imgs = [f for f in track_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
                if imgs:
                    clean_art = imgs[0]
                    break

    if clean_art is None:
        clean_art_candidates = [
            PROJECTS / f"single-{slug}" / "assets" / "images" / f"{slug}_raw.jpg",
            REPO / "project-assets" / "channel-branding" / "thumb_clean_base.jpg"
        ]
        for cand in clean_art_candidates:
            if cand.exists():
                clean_art = cand
                break

    if clean_art is None:
        clean_art = REPO / "project-assets" / "channel-branding" / "thumb_clean_base.jpg"

    # Always ensure thumbnail exists (clean style: raw art + official HUD badge only, NO text drawn over art)
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
                margin = 32
                pos_x = 1280 - hud_w - margin
                pos_y = 720 - hud_h - margin
                thumb.paste(hud_scaled, (pos_x, pos_y), hud_scaled)
            thumb.convert("RGB").save(thumb_out, "JPEG", quality=95)
            print(f"[single] Clean thumbnail generated without text: {thumb_out.name}")
        except Exception as e:
            print(f"[single] Warning: Failed to generate clean thumbnail: {e}")

    if out.exists() and not force:
        print(f"[single] Up to date: {out}")
        return out

    print(f"\n[single] === Rendering Visualizer for '{track['title']}' ===")
    print(f"[single] Artwork: {clean_art.name} | Master: {master.name}")

    # Official Character Clips pool for subtle overlay (all 7 clips shuffled per video)
    import random
    all_char_clips = list((REPO / "project-assets" / "channel-branding" / "videos").glob("*.mp4"))
    random.shuffle(all_char_clips)
    valid_char_clips = [c for c in all_char_clips if c.exists()]
    print(f"[single] Character clips shuffled ({len(valid_char_clips)} clips in rotation)")

    # Run the approved visualizer rendering script
    from visualizer_engine import render_visualizer_video
    render_visualizer_video(
        audio_path=master,
        clean_art_path=clean_art,
        output_path=out,
        char_clips=valid_char_clips,
        fps=fps,
        crf=crf,
        preset=preset
    )
    print(f"[single] Done! Deliverable: {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--song", help="Render specific song slug, or omit to render all")
    ap.add_argument("--all", action="store_true", help="Batch render all mastered songs")
    ap.add_argument("--limit", type=int, help="Limit number of songs in batch")
    ap.add_argument("--force", action="store_true", help="Force re-rendering")
    args = ap.parse_args()

    masters = load_masters()
    if args.song:
        render_single_song(args.song, force=args.force)
    elif args.all:
        tracks = masters[:args.limit] if args.limit else masters
        print(f"[single] Starting batch render of {len(tracks)} songs...")
        for i, t in enumerate(tracks, 1):
            print(f"\n[{i}/{len(tracks)}] Processing {t['title']}...")
            try:
                render_single_song(t["slug"], force=args.force)
            except Exception as e:
                print(f"[single] ERROR rendering {t['title']}: {e}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
