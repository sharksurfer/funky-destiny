#!/usr/bin/env python3
"""Join multi-part track audio files with seamless smart crossfade.

Features:
- Trims trailing silence on Part 1 (removes export quiet tails).
- Trims leading silence on Part 2 (removes dead time before first beat).
- Applies constant-power quarter-sine acrossfade (default: 3.0s).
- Exports full-resolution FLAC into the song directory and/or destination directory.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
ALBUM_2_DIR = REPO / "project-assets" / "album-2"


def get_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(audio_path)
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


def find_parts(track_dir: Path) -> tuple[Path | None, Path | None, str | None]:
    wavs = list(track_dir.glob("*.wav"))
    p1 = next((w for w in wavs if "parte 1" in w.name.lower() or "part 1" in w.name.lower()), None)
    p2 = next((w for w in wavs if "parte 2" in w.name.lower() or "part 2" in w.name.lower()), None)

    flac_name = None
    mds = list(track_dir.glob("*.md"))
    if mds:
        content = mds[0].read_text(encoding="utf-8")
        m = re.search(r"Nome do arquivo de áudio:\s*`([^`]+)`", content)
        if m:
            flac_name = m.group(1).strip()

    if not flac_name:
        # Fallback to dir name cleaned of leading number
        cleaned = re.sub(r"^\d+\s*-\s*", "", track_dir.name).strip()
        flac_name = f"{cleaned}.flac"

    return p1, p2, flac_name


def join_track_parts(
    part1: Path,
    part2: Path,
    output_flac: Path,
    fade_seconds: float = 3.0,
    force: bool = False
) -> Path:
    if output_flac.exists() and not force:
        print(f"[join] Already exists: {output_flac.name} ({get_duration(output_flac):.1f}s)")
        return output_flac

    output_flac.parent.mkdir(parents=True, exist_ok=True)
    d1 = get_duration(part1)
    d2 = get_duration(part2)
    print(f"\n[join] Processing: {output_flac.name}")
    print(f"[join]   Part 1: {part1.name} ({d1:.1f}s)")
    print(f"[join]   Part 2: {part2.name} ({d2:.1f}s)")
    print(f"[join]   Applying crossfade: {fade_seconds}s (quarter-sine constant power)...")

    # Filter chain:
    # 1. Truncate trailing silence from part 1 via areverse -> silenceremove -> areverse
    # 2. Truncate leading silence from part 2 (-45dB, 0.1s)
    # 3. acrossfade with quarter-sine curves (qsin) for constant power
    filter_complex = (
        "[0:a]areverse,silenceremove=start_periods=1:start_duration=0.2:start_threshold=-45dB,areverse[a0];"
        "[1:a]silenceremove=start_periods=1:start_duration=0.1:start_threshold=-45dB[a1];"
        f"[a0][a1]acrossfade=d={fade_seconds}:c1=qsin:c2=qsin[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(part1),
        "-i", str(part2),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "flac",
        str(output_flac)
    ]

    subprocess.run(cmd, check=True)
    final_dur = get_duration(output_flac)
    print(f"[join] -> SUCCESS: {output_flac.name} (Duration: {final_dur:.1f}s / {int(final_dur//60)}m{int(final_dur%60):02d}s)")
    return output_flac


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--album-dir", type=Path, default=ALBUM_2_DIR, help="Path to album folder")
    ap.add_argument("--fade", type=float, default=3.0, help="Crossfade duration in seconds (default: 3.0)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing output files")
    ap.add_argument("--copy-to-songs", action="store_true", help="Also copy merged FLAC to album's songs/ directory")
    args = ap.parse_args()

    album_dir = Path(args.album_dir).resolve()
    if not album_dir.exists():
        sys.exit(f"Album directory not found: {album_dir}")

    track_dirs = sorted([d for d in album_dir.iterdir() if d.is_dir() and d.name != "songs"])
    print(f"[join] Found {len(track_dirs)} track directories in {album_dir.name}")

    songs_dir = album_dir / "songs"
    if args.copy_to_songs:
        songs_dir.mkdir(parents=True, exist_ok=True)

    joined_count = 0
    for d in track_dirs:
        p1, p2, flac_name = find_parts(d)
        if not p1 or not p2:
            print(f"[join] Skipping {d.name}: parts missing (p1={bool(p1)}, p2={bool(p2)})")
            continue

        out_flac = d / flac_name
        joined = join_track_parts(p1, p2, out_flac, fade_seconds=args.fade, force=args.force)

        if args.copy_to_songs:
            import shutil
            dest = songs_dir / flac_name
            shutil.copy2(joined, dest)
            print(f"[join] Copied to songs pool: {dest.name}")

        joined_count += 1

    print(f"\n[join] Done! Merged {joined_count}/{len(track_dirs)} tracks successfully with {args.fade}s crossfade.")


if __name__ == "__main__":
    main()
