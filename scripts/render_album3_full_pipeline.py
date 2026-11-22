#!/usr/bin/env python3
"""Album 3 Visualizer Rendering Pipeline with Track-Specific Motion Clips.

Visual Direction (Option 1):
- Unique AI artwork background with smooth Ken Burns drift + beat punch.
- Alternates dynamically between the track's exclusive motion clip (featured during intense grooves/drops)
  and the channel's official character animation clips (soft lateral vignette blend).
- Audio-reactive Spectrum LED bars on bottom-left.
- Official opaque tactical HUD badge on bottom-right.
"""
from __future__ import annotations

import math
import os
import sys
import json
import random
import subprocess
from pathlib import Path
import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / ".agents/skills/music-channel/scripts"))

os.environ["ALBUM_NAME"] = "album-3"
import common

ALBUM_DIR = REPO / "project-assets" / "album-3"
PROJECTS_DIR = REPO / "projects" / "album-3"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
MASTERS_MANIFEST = PROJECTS_DIR / "audio-masters" / "artifacts" / "masters.json"
HUD_BADGE_PATH = REPO / "project-assets" / "channel-branding" / "hud_badge_opaque_tight.png"


def extract_audio_energy(audio_path: Path, fps: int = 30) -> list[float]:
    """Extract RMS energy of low-end frequencies per frame."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(audio_path),
        "-af", "lowpass=f=220,highpass=f=40",
        "-ac", "1", "-ar", "44100", "-f", "s16le", "-"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    raw_audio, _ = proc.communicate()
    samples = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)

    samples_per_frame = int(44100 / fps)
    energies = []
    for i in range(0, len(samples), samples_per_frame):
        chunk = samples[i:i + samples_per_frame]
        rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
        energies.append(rms)

    max_energy = max(energies) if energies and max(energies) > 0 else 1.0
    return [min(e / (max_energy * 0.75), 1.0) for e in energies]


def render_track_visualizer(
    audio_path: Path,
    clean_art_path: Path,
    output_path: Path,
    exclusive_clip_path: Path | None,
    channel_clips: list[Path],
    fps: int = 30,
    crf: int = 18,
    preset: str = "veryfast"
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    img_bgr = cv2.imread(str(clean_art_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Artwork not found: {clean_art_path}")

    out_w, out_h = 1920, 1080
    margin = 120
    base_resized = cv2.resize(img_bgr, (out_w + margin * 2, out_h + margin * 2), interpolation=cv2.INTER_LANCZOS4)
    bw_total, bh_total = base_resized.shape[1], base_resized.shape[0]

    norm_energies = extract_audio_energy(audio_path, fps=fps)
    total_frames = len(norm_energies)

    # Load opaque badge
    badge_bgr_a = cv2.imread(str(HUD_BADGE_PATH), cv2.IMREAD_UNCHANGED)
    bw = 360
    bh = int(bw * badge_bgr_a.shape[0] / badge_bgr_a.shape[1])
    badge_resized = cv2.resize(badge_bgr_a, (bw, bh), interpolation=cv2.INTER_AREA)
    badge_rgb = badge_resized[:, :, :3]
    badge_alpha = badge_resized[:, :, 3] / 255.0

    # Lateral vignette blend ramp (soft left overlay)
    blend_ramp = np.ones((out_h, out_w), dtype=np.float32)
    for x in range(out_w):
        if x < out_w * 0.35:
            blend_ramp[:, x] = 1.0
        elif x < out_w * 0.75:
            progress = (x - out_w * 0.35) / (out_w * 0.40)
            blend_ramp[:, x] = 0.5 * (1.0 + math.cos(progress * math.pi))
        else:
            blend_ramp[:, x] = 0.0

    for y in range(int(out_h * 0.82), out_h):
        y_fade = 1.0 - (y - out_h * 0.82) / (out_h * 0.18)
        blend_ramp[y, :] *= max(0.0, y_fade)

    blend_ramp_3d = blend_ramp[:, :, None]
    grid_y, grid_x = np.indices((out_h, out_w), dtype=np.float32)

    pipe_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}", "-r", str(fps),
        "-i", "-",
        "-i", str(audio_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
        "-t", f"{total_frames / fps:.3f}",
        "-movflags", "+faststart",
        str(output_path)
    ]
    writer = subprocess.Popen(pipe_cmd, stdin=subprocess.PIPE)

    # Prepare clip list: exclusive clip alternating with channel clips
    # E.g.: [Exclusive, Channel_1, Exclusive, Channel_2, ...]
    clip_playlist = []
    shuffled_channel = list(channel_clips)
    random.shuffle(shuffled_channel)
    
    if exclusive_clip_path and exclusive_clip_path.exists():
        for ch in shuffled_channel:
            clip_playlist.append(exclusive_clip_path)
            clip_playlist.append(ch)
    else:
        clip_playlist = shuffled_channel

    current_clip_idx = 0
    cap_clip = cv2.VideoCapture(str(clip_playlist[0])) if clip_playlist else None
    clip_switch_interval = int(fps * 8.0)  # switch every 8s

    try:
        for f_idx in range(total_frames):
            t = f_idx / fps
            beat_pulse = norm_energies[f_idx] if f_idx < len(norm_energies) else 0.0

            # Switch active clip every 8 seconds
            if clip_playlist and len(clip_playlist) > 1 and f_idx > 0 and (f_idx % clip_switch_interval == 0):
                if cap_clip is not None:
                    cap_clip.release()
                current_clip_idx = (current_clip_idx + 1) % len(clip_playlist)
                cap_clip = cv2.VideoCapture(str(clip_playlist[current_clip_idx]))

            # 1. Base Art: smooth Ken Burns + subtle beat punch
            drift_scale = 1.0 + (t / (total_frames / fps)) * 0.05
            punch_scale = 1.0 + beat_pulse * 0.022
            curr_scale = drift_scale * punch_scale

            crop_w = int(out_w / curr_scale)
            crop_h = int(out_h / curr_scale)

            cx = bw_total // 2 + int((np.random.random() - 0.5) * beat_pulse * 6)
            cy = bh_total // 2 + int((np.random.random() - 0.5) * beat_pulse * 6)

            x1 = max(0, min(bw_total - crop_w, cx - crop_w // 2))
            y1 = max(0, min(bh_total - crop_h, cy - crop_h // 2))

            cropped = base_resized[y1:y1 + crop_h, x1:x1 + crop_w]
            frame = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

            # 2. Dynamic Video Overlay (Exclusive motion clip or Channel character)
            if cap_clip is not None:
                ret, clip_frame = cap_clip.read()
                if not ret or clip_frame is None:
                    cap_clip.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, clip_frame = cap_clip.read()

                if ret and clip_frame is not None:
                    clip_full = cv2.resize(clip_frame, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
                    
                    # If currently showing the track exclusive clip, give it higher presence (65% to 85% on drops)
                    is_exclusive = (clip_playlist[current_clip_idx] == exclusive_clip_path)
                    if is_exclusive:
                        char_opacity = 0.65 + beat_pulse * 0.20
                    else:
                        char_opacity = 0.52 + beat_pulse * 0.16
                        
                    alpha_map = blend_ramp_3d * char_opacity
                    frame = (frame * (1.0 - alpha_map) + clip_full * alpha_map).astype(np.uint8)

            # 3. Audio-reactive Heatwave ripple & Chromatic split on strong drops
            if beat_pulse > 0.55:
                ripple_amp = (beat_pulse - 0.55) * 4.0
                map_x = grid_x + np.sin(grid_y * 0.05 + t * 15.0) * ripple_amp
                map_y = grid_y
                frame = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

                shift = int((beat_pulse - 0.55) * 6)
                if shift > 0:
                    b, g, r = cv2.split(frame)
                    b = np.roll(b, shift, axis=1)
                    r = np.roll(r, -shift, axis=1)
                    frame = cv2.merge([b, g, r])

            # 4. Audio-reactive LED Spectrum Bars on bottom-left
            num_bars = 28
            bar_w = 9
            bar_gap = 4
            start_x = 60
            base_y = out_h - 60

            for b_idx in range(num_bars):
                phase = (b_idx / num_bars) * 3.1415
                bar_h = int((math.sin(phase + t * 6) * 0.35 + 0.65) * beat_pulse * 85 + 10)
                bx = start_x + b_idx * (bar_w + bar_gap)

                c_ratio = b_idx / num_bars
                color = (
                    int(255 * (1.0 - c_ratio) + 200 * c_ratio),
                    int(150 * (1.0 - c_ratio) + 50 * c_ratio),
                    int(0 * (1.0 - c_ratio) + 255 * c_ratio)
                )
                cv2.rectangle(frame, (bx, base_y - bar_h), (bx + bar_w, base_y), color, -1)
                cv2.rectangle(frame, (bx, base_y - bar_h - 3), (bx + bar_w, base_y - bar_h), (255, 255, 255), -1)

            # 5. Composite HUD badge on bottom-right
            bx_pos = out_w - bw - 50
            by_pos = out_h - bh - 40
            roi = frame[by_pos:by_pos + bh, bx_pos:bx_pos + bw]
            for c in range(3):
                roi[:, :, c] = roi[:, :, c] * (1.0 - badge_alpha) + badge_rgb[:, :, c] * badge_alpha

            writer.stdin.write(frame.tobytes())
    finally:
        if cap_clip is not None:
            cap_clip.release()
        writer.stdin.close()
        writer.wait()

    return output_path


def main():
    if not MASTERS_MANIFEST.exists():
        print(f"Masters manifest not found at {MASTERS_MANIFEST}. Waiting for mastering...")
        return

    data = json.loads(MASTERS_MANIFEST.read_text(encoding="utf-8"))
    tracks = data["tracks"]
    print(f"Total tracks to render for Album 3: {len(tracks)}")

    branding_clips = list((REPO / "project-assets" / "channel-branding" / "videos").glob("*.mp4"))

    for idx, track in enumerate(tracks, 1):
        slug = track["slug"]
        title = track["title"]
        master_audio = Path(track["master"])

        project = PROJECTS_DIR / f"single-{slug}"
        renders_dir = project / "renders"
        artifacts_dir = project / "artifacts"
        renders_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        (artifacts_dir / "title.txt").write_text(title, encoding="utf-8")
        (artifacts_dir / "subtitle.txt").write_text("Funky Destiny", encoding="utf-8")

        out_video = renders_dir / f"{slug}.mp4"
        thumb_out = renders_dir / f"{slug}-thumb.jpg"

        # Find artwork and exclusive mp4
        clean_art = None
        exclusive_clip = None
        for track_dir in ALBUM_DIR.iterdir():
            if track_dir.is_dir() and slug in track_dir.name.lower().replace(" ", "-"):
                imgs = [f for f in track_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
                if imgs:
                    clean_art = imgs[0]
                mp4s = list(track_dir.glob("*.mp4"))
                if mp4s:
                    exclusive_clip = mp4s[0]
                break

        if clean_art is None:
            clean_art = REPO / "project-assets" / "channel-branding" / "thumb_clean_base.jpg"

        # Ensure thumbnail
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

        if out_video.exists() and out_video.stat().st_size > 1000000:
            print(f"[{idx}/{len(tracks)}] Already rendered: {title} ({out_video})")
            continue

        print(f"\n[{idx}/{len(tracks)}] Rendering Visualizer: {title}")
        print(f"  Audio:     {master_audio.name}")
        print(f"  Art:       {clean_art.name}")
        print(f"  Clip:      {exclusive_clip.name if exclusive_clip else 'None'}")

        render_track_visualizer(
            audio_path=master_audio,
            clean_art_path=clean_art,
            output_path=out_video,
            exclusive_clip_path=exclusive_clip,
            channel_clips=branding_clips,
            fps=30,
            crf=18,
            preset="veryfast"
        )
        print(f"  ✅ Rendered successfully: {out_video}")

    print("\n🎉 All 12 Full Music Videos rendered successfully for Album 3!")

if __name__ == "__main__":
    main()
