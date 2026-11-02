"""Audio-Reactive Visualizer Engine for YouTube Singles.

Implements the official approved visualizer format for Funky Destiny:
- Clean 1080p unique AI artwork background with smooth Ken Burns drift + beat punch.
- Official Character Animation overlay in native 16:9 scale with soft lateral vignette blend (52-70% opacity).
- Audio-reactive subtle heatwave distortion and chromatic split on strong bass drops.
- Equalizer LED frequency spectrum on bottom-left.
- Official solid opaque HUD badge on bottom-right.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
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


def render_visualizer_video(
    audio_path: Path,
    clean_art_path: Path,
    output_path: Path,
    char_clips: list[Path],
    fps: int = 30,
    crf: int = 18,
    preset: str = "medium",
    duration: float | None = None
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Base art setup
    img_bgr = cv2.imread(str(clean_art_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Artwork not found: {clean_art_path}")

    out_w, out_h = 1920, 1080
    margin = 120
    base_resized = cv2.resize(img_bgr, (out_w + margin * 2, out_h + margin * 2), interpolation=cv2.INTER_LANCZOS4)
    bw_total, bh_total = base_resized.shape[1], base_resized.shape[0]

    # 2. Extract audio energy
    norm_energies = extract_audio_energy(audio_path, fps=fps)
    total_frames = len(norm_energies) if duration is None else int(duration * fps)

    # 3. Load opaque badge
    badge_bgr_a = cv2.imread(str(HUD_BADGE_PATH), cv2.IMREAD_UNCHANGED)
    bw = 360
    bh = int(bw * badge_bgr_a.shape[0] / badge_bgr_a.shape[1])
    badge_resized = cv2.resize(badge_bgr_a, (bw, bh), interpolation=cv2.INTER_AREA)
    badge_rgb = badge_resized[:, :, :3]
    badge_alpha = badge_resized[:, :, 3] / 255.0

    # 4. Horizontal blend ramp for character overlay
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

    # 5. FFmpeg pipe writer
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

    # Setup character capture
    current_clip_idx = 0
    cap_clip = cv2.VideoCapture(str(char_clips[0])) if char_clips else None
    clip_switch_interval = int(fps * 8.0)

    try:
        for f_idx in range(total_frames):
            t = f_idx / fps
            beat_pulse = norm_energies[f_idx] if f_idx < len(norm_energies) else 0.0

            # Rotate character clips every 8 seconds
            if char_clips and len(char_clips) > 1 and f_idx > 0 and (f_idx % clip_switch_interval == 0):
                if cap_clip is not None:
                    cap_clip.release()
                current_clip_idx = (current_clip_idx + 1) % len(char_clips)
                cap_clip = cv2.VideoCapture(str(char_clips[current_clip_idx]))

            # 1. Base art with slow Ken Burns + Beat Punch
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

            # 2. Character animation overlay
            if cap_clip is not None:
                ret, clip_frame = cap_clip.read()
                if not ret or clip_frame is None:
                    cap_clip.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, clip_frame = cap_clip.read()

                if ret and clip_frame is not None:
                    clip_full = cv2.resize(clip_frame, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
                    char_opacity = 0.52 + beat_pulse * 0.16
                    alpha_map = blend_ramp_3d * char_opacity
                    frame = (frame * (1.0 - alpha_map) + clip_full * alpha_map).astype(np.uint8)

            # 3. Audio-reactive Heatwave ripple & Chromatic split
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

            # 4. Audio-reactive Spectrum Bars on bottom-left
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
            frame[by_pos:by_pos + bh, bx_pos:bx_pos + bw] = roi

            writer.stdin.write(frame.tobytes())
    finally:
        if cap_clip is not None:
            cap_clip.release()
        writer.stdin.close()
        writer.wait()

    return output_path
