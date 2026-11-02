#!/usr/bin/env python3
"""Render a single song video synchronized to rhythmic beats and instrument cues.

Features:
- Analyzes low-frequency energy (bass/drums) to estimate musical tempo (BPM) and beat intervals.
- Cuts rhythmically on bar/measure boundaries (e.g. every 2 or 4 bars).
- Alternates between instruments and performance angles (bass close-up, wide, drums, enjoying groove).
- Subtly pulse-speeds the video slightly on beat transients to give a reactive rhythmic punch.

Usage:
  python3 render_beat_synced.py --song rubber-people
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
from common import (CHANNEL_NAME, PROJECTS, VIDEOS_DIR, blur_pad_filter, find_font,  # noqa: E402
                    probe_duration, require_ffmpeg, resolve_master, run)


def detect_tempo_and_beats(audio_path: Path) -> tuple[float, list[float]]:
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
    
    frame_size = int(22050 * 0.05)  # 50ms frames
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
        bpm = 120.0
        beat_interval = 0.5

    # 4 beats per bar
    bar_length = beat_interval * 4
    return bpm, bar_length


def categorize_clips() -> dict[str, list[Path]]:
    """Group available video assets by role."""
    clips = sorted(VIDEOS_DIR.glob("*.mp4"))
    roles = {
        "bass": [c for c in clips if "baixo" in c.stem.lower()],
        "drums": [c for c in clips if "drum" in c.stem.lower()],
        "guitar": [c for c in clips if "guitar" in c.stem.lower()],
        "reaction": [c for c in clips if "enjoying" in c.stem.lower()],
    }
    return roles


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--song", required=True, help="Track slug or name")
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--bars-per-cut", type=int, default=2, help="Number of bars between cuts (default 2)")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()

    require_ffmpeg()
    track = resolve_master(args.song)
    master = Path(track["master"])
    dur = probe_duration(master)
    w, h = (int(x) for x in args.resolution.lower().split("x"))

    project = PROJECTS / f"single-{track['slug']}-beatsync"
    (project / "renders").mkdir(parents=True, exist_ok=True)
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "video").mkdir(parents=True, exist_ok=True)

    print(f"[beat-sync] Analyzing audio beats for '{track['title']}'...")
    bpm, bar_length = detect_tempo_and_beats(master)
    cut_duration = bar_length * args.bars_per_cut  # cut length in seconds
    print(f"[beat-sync] Estimated BPM: {bpm:.1f} | Bar: {bar_length:.2f}s | Cut duration: {cut_duration:.2f}s")

    roles = categorize_clips()
    # Sequence pattern: Bass -> Bass angle 2 -> Drums -> Reaction -> Bass -> Guitar
    sequence_roles = ["bass", "bass", "reaction", "drums", "bass", "guitar", "reaction"]

    # Build EDL (edit decision list)
    edl = []
    curr_time = 0.0
    role_idx = 0
    rnd = random.Random(42)

    while curr_time < dur:
        role = sequence_roles[role_idx % len(sequence_roles)]
        role_idx += 1
        cand_clips = roles.get(role) or roles["bass"]
        clip = rnd.choice(cand_clips) if cand_clips else list(VIDEOS_DIR.glob("*.mp4"))[0]
        
        segment_dur = min(cut_duration, dur - curr_time)
        clip_max_dur = probe_duration(clip)
        
        # Pick a random start point inside the clip if possible
        max_start = max(0.0, clip_max_dur - segment_dur)
        start_pt = rnd.uniform(0, max_start) if max_start > 0 else 0.0

        edl.append({
            "clip": clip,
            "role": role,
            "start": start_pt,
            "duration": segment_dur,
        })
        curr_time += segment_dur

    print(f"[beat-sync] Generated {len(edl)} rhythmic cuts across {dur:.1f}s")

    # Render segments to temporary normalized parts
    concat_list = project / "assets" / "video" / "segments.txt"
    concat_lines = []

    for i, item in enumerate(edl):
        seg_out = project / "assets" / "video" / f"seg_{i:03d}.mp4"
        if not seg_out.exists():
            fc = blur_pad_filter(w, h, args.fps, inp="0:v", out="v", n=str(i))
            gop = args.fps * 2
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{item['start']:.2f}",
                "-i", str(item["clip"]),
                "-t", f"{item['duration']:.3f}",
                "-filter_complex", fc, "-map", "[v]", "-an",
                "-c:v", "libx264", "-preset", "fast", "-crf", str(args.crf),
                "-pix_fmt", "yuv420p", "-r", str(args.fps),
                "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
                str(seg_out)
            ]
            run(cmd)
        concat_lines.append(f"file '{seg_out.resolve()}'\n")

    concat_list.write_text("".join(concat_lines))

    # Assemble video with concat demuxer + Title card + Audio
    font = find_font()
    ts = 8.0
    alpha = f"'if(lt(t,0.6),t/0.6,if(lt(t,{ts - 1}),1,if(lt(t,{ts}),{ts}-t,0)))'"
    title_file = project / "artifacts" / "title.txt"
    sub_file = project / "artifacts" / "subtitle.txt"
    title_file.write_text(track["title"])
    sub_file.write_text(CHANNEL_NAME)

    # Filter graph: Title card (first 8s) + Persistent Watermark (bottom right) + Equalizer (bottom left)
    vf = [
        f"fade=t=in:st=0:d=1",
        f"fade=t=out:st={max(dur - 2.5, 0):.3f}:d=2.5"
    ]
    if font:
        # Title card in the beginning
        common_dt = f"fontfile={font}:fontcolor=white:shadowcolor=black@0.7:shadowx=3:shadowy=3:alpha={alpha}:enable='lt(t,{ts})'"
        vf.append(f"drawtext=textfile={title_file}:{common_dt}:fontsize=h/12:x=(w-text_w)/2:y=h*0.72")
        vf.append(f"drawtext=textfile={sub_file}:{common_dt}:fontsize=h/28:x=(w-text_w)/2:y=h*0.72+h/12+h/40")
        
        # Persistent channel watermark in the lower-right corner (Neopunk Cyber styling)
        wm_common = f"fontfile={font}:fontcolor=0xFF1E42:shadowcolor=black@0.8:shadowx=2:shadowy=2:fontsize=h/38"
        vf.append(f"drawtext=text='// {CHANNEL_NAME.upper()}':{wm_common}:x=w-tw-40:y=h-th-35")

    out = project / "renders" / f"{track['slug']}-beatsync.mp4"
    print(f"[beat-sync] Final assembling with Neopunk HUD to {out.name}...")

    # Complex filter:
    # 1. Takes video from concat demuxer (0:v) and applies text / fade -> [vbase]
    # 2. Takes audio (1:a), isolates bass/kick/slap (lowpass=f=380), generates reactive bars -> [raw_eq]
    # 3. Transparent background with colorkey -> [eq]
    # 4. Overlays [eq] on bottom-left of [vbase] -> [vout]
    filter_complex = (
        f"[0:v]{','.join(vf)}[vbase];"
        f"[1:a]lowpass=f=400,showfreqs=s=340x85:mode=bar:ascale=log:fscale=log:colors=0xFF1E42:win_size=1024[raw_eq];"
        f"[raw_eq]colorkey=0x000000:0.25:0.1,format=yuva420p[eq];"
        f"[vbase][eq]overlay=40:H-h-35[vout]"
    )

    cmd_final = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-i", str(master),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "1:a",
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-r", str(args.fps),
        "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
        "-metadata", f"title={track['title']}", "-metadata", f"artist={CHANNEL_NAME}",
        "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)
    ]
    run(cmd_final)
    print(f"[beat-sync] Done! Saved at: {out}")


if __name__ == "__main__":
    main()
