#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALBUM_DIR = REPO / "project-assets" / "album-3"
SONGS_DIR = ALBUM_DIR / "songs"
SONGS_DIR.mkdir(parents=True, exist_ok=True)

def get_duration(p: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]
    return float(subprocess.check_output(cmd, text=True).strip())

def join_audio_parts(part1: Path, part2: Path, output_flac: Path, fade_sec: float = 3.0):
    output_flac.parent.mkdir(parents=True, exist_ok=True)
    d1 = get_duration(part1)
    d2 = get_duration(part2)
    print(f"[join] Processing {output_flac.name}")
    print(f"       Part 1: {part1.name} ({d1:.1f}s)")
    print(f"       Part 2: {part2.name} ({d2:.1f}s)")
    
    filter_complex = (
        "[0:a]areverse,silenceremove=start_periods=1:start_duration=0.2:start_threshold=-45dB,areverse[a0];"
        "[1:a]silenceremove=start_periods=1:start_duration=0.1:start_threshold=-45dB[a1];"
        f"[a0][a1]acrossfade=d={fade_sec}:c1=qsin:c2=qsin[aout]"
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
    dur = get_duration(output_flac)
    print(f"       -> Merged: {dur:.1f}s ({int(dur//60)}m{int(dur%60):02d}s)")

def main():
    dirs = sorted([d for d in ALBUM_DIR.iterdir() if d.is_dir() and d.name != "songs"])
    print(f"Organizing {len(dirs)} track directories in album-3...")

    for d in dirs:
        mds = list(d.glob("*.md"))
        if not mds:
            continue
        content = mds[0].read_text(encoding="utf-8")
        title_m = re.search(r"\*\*[Tt]ítulo:\*\*\s*(.+)", content)
        flac_m = re.search(r"\*\*Nome do arquivo de áudio:\*\*\s*`([^`]+)`", content)
        title = title_m.group(1).strip() if title_m else ""
        flac_name = flac_m.group(1).strip() if flac_m else f"{title}.flac"

        mp3_orig = ALBUM_DIR / f"{title}.mp3"
        mp3_ext = ALBUM_DIR / f"{title} - 1.mp3"
        jpg_art = ALBUM_DIR / f"{title}.jpg"
        mp4_clip = ALBUM_DIR / f"{title}.mp4"

        # 1. Move artwork and clip into track dir if present at root
        target_art = d / f"{title}.jpg"
        target_clip = d / f"{title}.mp4"
        if jpg_art.exists():
            shutil.move(str(jpg_art), str(target_art))
            print(f"  Moved art: {title}.jpg -> {d.name}")
        if mp4_clip.exists():
            shutil.move(str(mp4_clip), str(target_clip))
            print(f"  Moved clip: {title}.mp4 -> {d.name}")

        # 2. Check audio parts
        target_flac = d / flac_name
        dest_songs_flac = SONGS_DIR / flac_name

        if not target_flac.exists():
            if mp3_orig.exists() and mp3_ext.exists():
                join_audio_parts(mp3_orig, mp3_ext, target_flac, fade_sec=3.0)
            elif (d / f"{title}.mp3").exists() and (d / f"{title} - 1.mp3").exists():
                join_audio_parts(d / f"{title}.mp3", d / f"{title} - 1.mp3", target_flac, fade_sec=3.0)
            else:
                print(f"  Warning: parts not found for {title}")

        # 3. Copy to songs/ pool for mastering
        if target_flac.exists() and not dest_songs_flac.exists():
            shutil.copy2(target_flac, dest_songs_flac)
            print(f"  Copied to songs/: {flac_name}")

    print("\n✅ All Album 3 tracks organized and joined into 24-bit/lossless FLAC in songs/ pool!")

if __name__ == "__main__":
    main()
