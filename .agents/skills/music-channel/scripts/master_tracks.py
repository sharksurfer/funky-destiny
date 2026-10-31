#!/usr/bin/env python3
"""Master audio tracks for YouTube: detect abrupt endings, fade out the last N
seconds, normalize loudness (two-pass loudnorm) and write 48 kHz/24-bit FLAC.

Writes:
  projects/audio-masters/assets/audio/<slug>.flac
  projects/audio-masters/artifacts/masters.json   (consumed by render/mix scripts)

Examples:
  python3 master_tracks.py --dry-run              # analyze only, no files written
  python3 master_tracks.py                        # auto: fade only abrupt endings
  python3 master_tracks.py --fade-policy all      # fade every song
  python3 master_tracks.py --only "track title" --force
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (MASTERS_DIR, MASTERS_MANIFEST, SONGS_DIR, measure_loudness,  # noqa: E402
                    parse_song_filename, probe_duration, require_ffmpeg, run, tail_rms_db)

AUDIO_EXTS = {".flac", ".wav", ".mp3", ".m4a", ".aiff", ".ogg"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-dir", type=Path, default=SONGS_DIR)
    ap.add_argument("--out-dir", type=Path, default=MASTERS_DIR)
    ap.add_argument("--fade", type=float, default=5.0, help="Fade-out length in seconds (default 5)")
    ap.add_argument("--fade-policy", choices=["auto", "all", "none"], default="auto",
                    help="auto = fade only tracks whose ending is abrupt (default)")
    ap.add_argument("--abrupt-threshold-db", type=float, default=-35.0,
                    help="Tail RMS above this (dBFS) = abrupt ending (default -35)")
    ap.add_argument("--tail-window", type=float, default=0.5, help="Seconds analyzed at the end")
    ap.add_argument("--lufs", type=float, default=-14.0, help="Integrated loudness target")
    ap.add_argument("--tp", type=float, default=-1.0, help="True-peak ceiling (dBTP)")
    ap.add_argument("--no-normalize", action="store_true", help="Skip loudness normalization")
    ap.add_argument("--only", help="Process only files whose name contains this text")
    ap.add_argument("--force", action="store_true", help="Re-render even if master is up to date")
    ap.add_argument("--dry-run", action="store_true", help="Analyze and report only")
    args = ap.parse_args()

    require_ffmpeg()
    sources = sorted(p for p in args.input_dir.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if args.only:
        sources = [p for p in sources if args.only.lower() in p.name.lower()]
    if not sources:
        sys.exit("[channel] No audio files found.")

    # Merge into existing manifest so partial runs (--only) don't drop other tracks.
    existing = {}
    if MASTERS_MANIFEST.exists():
        existing = {t["slug"]: t for t in json.loads(MASTERS_MANIFEST.read_text())["tracks"]}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{'dur':>7} {'tailRMS':>8} {'abrupt':>6} {'fade':>4} {'inLUFS':>7} {'outLUFS':>7}  title")
    total = 0.0
    for src in sources:
        meta = parse_song_filename(src)
        dur = probe_duration(src)
        total += dur
        tail = tail_rms_db(src, args.tail_window)
        abrupt = tail > args.abrupt_threshold_db
        fade = args.fade_policy == "all" or (args.fade_policy == "auto" and abrupt)
        fade = fade and dur > args.fade * 2
        out = args.out_dir / f"{meta['slug']}.flac"

        entry = {
            **meta,
            "source": str(src),
            "master": str(out),
            "duration": round(dur, 3),
            "tail_rms_db": None if math.isinf(tail) else round(tail, 1),
            "abrupt_ending": abrupt,
            "fade_out_applied": fade,
            "fade_seconds": args.fade if fade else 0,
        }

        up_to_date = out.exists() and out.stat().st_mtime > src.stat().st_mtime and not args.force
        if args.dry_run or up_to_date:
            prev = existing.get(meta["slug"], {})
            entry.update({k: prev.get(k) for k in ("input_lufs", "output_lufs", "output_tp")})
            if up_to_date and prev:
                entry.update({k: prev[k] for k in ("fade_out_applied", "fade_seconds") if k in prev})
            tag = "dry" if args.dry_run else "skip"
            print(f"{dur:7.1f} {tail:8.1f} {str(abrupt):>6} {str(entry['fade_out_applied']):>4} "
                  f"{'-':>7} {'-':>7}  [{tag}] {meta['title']}")
            if not args.dry_run:
                existing[meta["slug"]] = entry
            continue

        filters = []
        if not args.no_normalize:
            m = measure_loudness(src, args.lufs, args.tp)
            entry["input_lufs"] = float(m["input_i"])
            filters.append(
                f"loudnorm=I={args.lufs}:TP={args.tp}:LRA=11"
                f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                f":offset={m['target_offset']}:linear=true"
            )
        filters.append("aresample=48000")
        if fade:
            # Fade is applied AFTER loudnorm so the normalizer never "sees" the fade.
            filters.append(f"afade=t=out:st={dur - args.fade:.3f}:d={args.fade}")

        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
             "-af", ",".join(filters), "-ac", "2", "-ar", "48000",
             "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24",
             "-map_metadata", "-1", "-metadata", f"title={meta['title']}",
             "-metadata", f"artist={meta['artist'] or ''}", str(out)])

        post = measure_loudness(out, args.lufs, args.tp)
        entry["output_lufs"] = float(post["input_i"])
        entry["output_tp"] = float(post["input_tp"])
        existing[meta["slug"]] = entry
        print(f"{dur:7.1f} {tail:8.1f} {str(abrupt):>6} {str(fade):>4} "
              f"{entry.get('input_lufs', 0):7.1f} {entry['output_lufs']:7.1f}  {meta['title']}")

    print(f"\nTotal source duration: {total/60:.1f} min ({total:.0f} s) across {len(sources)} tracks")
    if args.dry_run:
        print("[dry-run] No files written.")
        return

    MASTERS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tracks = sorted(existing.values(), key=lambda t: t["title"].lower())
    MASTERS_MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {"lufs": args.lufs, "tp": args.tp, "fade": args.fade,
                     "fade_policy": args.fade_policy, "normalize": not args.no_normalize,
                     "abrupt_threshold_db": args.abrupt_threshold_db},
        "tracks": tracks,
    }, indent=2, ensure_ascii=False))
    print(f"Manifest: {MASTERS_MANIFEST}")


if __name__ == "__main__":
    main()
