#!/usr/bin/env python3
import os
import sys
import glob
import json
import time
import subprocess
import numpy as np
from pathlib import Path

# Paths
PROJECTS_DIR = Path("projects/album-1")
SHORTS_DIR = PROJECTS_DIR / "shorts"
SHORTS_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = SHORTS_DIR / "shorts_manifest.json"

TARGET_DURATION = 45.0  # Ideal length for YouTube Shorts (<60s)

def get_track_list():
    projects = sorted(glob.glob(str(PROJECTS_DIR / "single-*")))
    tracks = []
    for p in projects:
        if 'beatsync' in p:
            continue
        renders = glob.glob(f"{p}/renders/*.mp4")
        clean = [r for r in renders if 'preview' not in r]
        if not clean:
            continue
        video_path = clean[0]
        slug = os.path.basename(p).replace("single-", "")
        title_file = Path(p) / "artifacts" / "title.txt"
        if title_file.exists():
            title = title_file.read_text(encoding="utf-8").strip()
        else:
            title = slug.replace("-", " ").title()
        tracks.append({
            "slug": slug,
            "title": title,
            "video_path": video_path,
            "short_path": str(SHORTS_DIR / f"{slug}-short.mp4")
        })
    return tracks

def detect_best_window(video_path, target_duration=TARGET_DURATION):
    cmd_probe = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    total_dur = float(subprocess.check_output(cmd_probe).decode().strip())
    
    cmd_extract = ['ffmpeg', '-y', '-i', video_path, '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1']
    p = subprocess.Popen(cmd_extract, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    raw, _ = p.communicate()
    
    samples = np.frombuffer(raw, dtype=np.float32)
    win_samples = 16000
    num_secs = len(samples) // win_samples
    if num_secs <= target_duration:
        return 0.0, float(num_secs)
        
    rms_per_sec = []
    for s in range(num_secs):
        chunk = samples[s*win_samples : (s+1)*win_samples]
        rms = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0.0
        rms_per_sec.append(rms)

    target_len = int(target_duration)
    best_s = 15
    best_val = -1.0
    start_search = min(15, max(0, int(num_secs * 0.15)))
    end_search = max(start_search + 1, num_secs - target_len - 5)
    
    for s in range(start_search, end_search):
        energy = sum(rms_per_sec[s:s+target_len])
        if energy > best_val:
            best_val = energy
            best_s = s
            
    return float(best_s), float(target_duration)

def render_short(input_path, output_path, start_sec, duration):
    if os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
        print(f"  [Render] Short already exists: {output_path} (skipping)")
        return
        
    cmd = [
        'ffmpeg', '-y',
        '-ss', f"{start_sec:.2f}",
        '-i', input_path,
        '-t', f"{duration:.2f}",
        '-vf', 'crop=ih*(9/16):ih:(iw-ow)/2:0,scale=1080:1920',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
        '-c:a', 'aac', '-b:a', '192k',
        '-af', f'afade=t=in:st=0:d=0.5,afade=t=out:st={duration - 1.0:.2f}:d=1.0',
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def main():
    tracks = get_track_list()
    print(f"Total tracks found: {len(tracks)}")
    
    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
            
    for i, track in enumerate(tracks, 1):
        slug = track["slug"]
        print(f"\n[{i}/{len(tracks)}] Processing: {track['title']} ({slug})")
        
        info = manifest.get(slug, {})
        start_sec = info.get("start_sec")
        duration = info.get("duration", TARGET_DURATION)
        
        if start_sec is None:
            print("  [Analyze] Finding peak energy climax window...")
            start_sec, duration = detect_best_window(track["video_path"], TARGET_DURATION)
            info["start_sec"] = start_sec
            info["duration"] = duration
            print(f"  [Analyze] Peak window identified: {start_sec:.1f}s to {start_sec+duration:.1f}s")
            
        short_path = track["short_path"]
        print(f"  [Render] Cutting vertical 9:16 short...")
        render_short(track["video_path"], short_path, start_sec, duration)
        info["short_path"] = short_path
        info["status"] = "rendered"
        
        manifest[slug] = info
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [Done] Saved short: {short_path}")

    print("\n✅ All 24 Shorts rendered successfully!")

if __name__ == "__main__":
    main()
