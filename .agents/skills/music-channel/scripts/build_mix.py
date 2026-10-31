#!/usr/bin/env python3
"""Build the 1h+ compilation video from the mastered tracks.

Pipeline (fast — the long video is never re-encoded frame by frame):
  1. Order tracks (catalog / shuffle / explicit file) and enforce min duration.
  2. Concatenate masters into one audio file (silence gap OR crossfade).
  3. Encode a short visual loop once from the clips (fixed GOP).
  4. Repeat the loop with the concat demuxer (-c copy) and mux the audio.
  5. Write YouTube chapters + tracklist JSON.

Writes under projects/<project>/ (default: mix-<date>):
  assets/audio/mix.flac, assets/video/loop.mp4, renders/<project>.mp4,
  artifacts/chapters.txt, artifacts/tracklist.json

Examples:
  python3 build_mix.py --dry-run                       # just print order + chapters
  python3 build_mix.py --order shuffle --seed 7
  python3 build_mix.py --order file --order-file my_order.txt --crossfade 3
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PROJECTS, build_visual_loop, collect_clips, fmt_ts,  # noqa: E402
                    load_masters, probe_duration, require_ffmpeg, run)


def order_tracks(tracks: list[dict], mode: str, seed: int | None, order_file: Path | None) -> list[dict]:
    if mode == "catalog":
        return list(tracks)
    if mode == "shuffle":
        rnd = random.Random(seed)
        out = list(tracks)
        rnd.shuffle(out)
        return out
    by_slug = {t["slug"]: t for t in tracks}
    lines = [l.strip() for l in order_file.read_text().splitlines() if l.strip() and not l.startswith("#")]
    missing = [l for l in lines if l not in by_slug]
    if missing:
        sys.exit(f"[channel] Unknown slugs in order file: {missing}")
    return [by_slug[l] for l in lines]


def extend_to_min(ordered: list[dict], min_dur: float, gap: float, xf: float, seed: int | None) -> list[dict]:
    """Append reshuffled passes (no back-to-back repeat at the seam) until long enough."""
    rnd = random.Random(seed)
    out = list(ordered)
    while total_duration(out, gap, xf) < min_dur:
        extra = list(ordered)
        rnd.shuffle(extra)
        if extra[0]["slug"] == out[-1]["slug"] and len(extra) > 1:
            extra[0], extra[1] = extra[1], extra[0]
        for t in extra:
            out.append(t)
            if total_duration(out, gap, xf) >= min_dur:
                break
    return out


def total_duration(tracks: list[dict], gap: float, xf: float) -> float:
    d = sum(t["duration"] for t in tracks)
    joins = max(len(tracks) - 1, 0)
    return d - joins * xf if xf > 0 else d + joins * gap


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=f"mix-{date.today().isoformat()}")
    ap.add_argument("--order", choices=["catalog", "shuffle", "file"], default="shuffle")
    ap.add_argument("--order-file", type=Path, help="One slug per line (with --order file)")
    ap.add_argument("--seed", type=int, default=None, help="Shuffle seed (reproducible order)")
    ap.add_argument("--gap", type=float, default=1.0, help="Silence between tracks (s)")
    ap.add_argument("--crossfade", type=float, default=0.0, help="Crossfade length (s); overrides --gap")
    ap.add_argument("--min-duration", type=float, default=3660.0,
                    help="Minimum total length in seconds (default 3660 = 1h01m)")
    ap.add_argument("--fill", choices=["repeat", "fail", "allow-short"], default="fail",
                    help="If shorter than min: repeat tracks, fail (default) or accept")
    ap.add_argument("--clips", nargs="*", help="Clips for the visual loop (default: all in project-assets/videos)")
    ap.add_argument("--clip-seconds", type=float, default=8.0, help="Max seconds used from each clip")
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.order == "file" and not args.order_file:
        sys.exit("[channel] --order file requires --order-file")
    require_ffmpeg()

    tracks = load_masters()
    for t in tracks:  # trust the actual file, not the cached number
        if Path(t["master"]).exists():
            t["duration"] = probe_duration(Path(t["master"]))
        else:
            sys.exit(f"[channel] Master missing: {t['master']} — run master_tracks.py")

    ordered = order_tracks(tracks, args.order, args.seed, args.order_file)
    gap, xf = (0.0, args.crossfade) if args.crossfade > 0 else (args.gap, 0.0)
    total = total_duration(ordered, gap, xf)
    if total < args.min_duration:
        msg = (f"[channel] Mix is {total/60:.1f} min, below minimum {args.min_duration/60:.1f} min.")
        if args.fill == "fail":
            sys.exit(msg + " Use --fill repeat (append reshuffled tracks) or --fill allow-short.")
        if args.fill == "repeat":
            ordered = extend_to_min(ordered, args.min_duration, gap, xf, args.seed)
            total = total_duration(ordered, gap, xf)
            print(msg + f" Extended with repeats → {len(ordered)} entries, {total/60:.1f} min.")
        else:
            print(msg + " Proceeding (allow-short).")

    # Chapters
    force_h = total >= 3600
    starts, cursor = [], 0.0
    for t in ordered:
        starts.append(cursor)
        cursor += t["duration"] - xf if xf else t["duration"] + gap
    chapters = [f"{fmt_ts(s, force_h)} {t['title']}" for s, t in zip(starts, ordered)]
    short = [t["title"] for t in ordered if t["duration"] < 10]
    if short:
        print(f"[channel] WARNING: YouTube chapters need ≥10 s each; too short: {short}")

    print(f"\nOrder ({len(ordered)} entries, total {fmt_ts(total, True)}):")
    print("\n".join(chapters))
    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    project = PROJECTS / args.project
    for sub in ("assets/audio", "assets/video", "artifacts", "renders"):
        (project / sub).mkdir(parents=True, exist_ok=True)

    # 1) Audio
    mix = project / "assets" / "audio" / "mix.flac"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    for t in ordered:
        cmd += ["-i", t["master"]]
    n = len(ordered)
    if xf:
        parts, prev = [], "[0:a]"
        for i in range(1, n):
            label = f"[x{i}]" if i < n - 1 else "[aout]"
            parts.append(f"{prev}[{i}:a]acrossfade=d={xf}:c1=tri:c2=tri{label}")
            prev = label
        graph = ";".join(parts) if n > 1 else "[0:a]anull[aout]"
    else:
        pad = [f"[{i}:a]apad=pad_dur={gap}[p{i}]" for i in range(n - 1)]
        ins = "".join(f"[p{i}]" for i in range(n - 1)) + f"[{n-1}:a]"
        graph = ";".join(pad + [f"{ins}concat=n={n}:v=0:a=1[aout]"])
    cmd += ["-filter_complex", graph, "-map", "[aout]", "-ar", "48000", "-ac", "2",
            "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24", str(mix)]
    print("\n[channel] Concatenating audio…")
    run(cmd)
    audio_dur = probe_duration(mix)

    # 2) Visual loop (encoded once)
    clips = collect_clips(args.clips)
    w, h = (int(x) for x in args.resolution.lower().split("x"))
    loop = project / "assets" / "video" / "loop.mp4"
    print(f"[channel] Encoding visual loop from {len(clips)} clip(s)…")
    loop_dur = build_visual_loop(clips, loop, w, h, args.fps, clip_seconds=args.clip_seconds,
                                 crf=args.crf, preset=args.preset)

    # 3) Repeat loop with stream copy + mux audio
    reps = math.ceil(audio_dur / loop_dur) + 1
    concat_list = project / "assets" / "video" / "loop_concat.txt"
    concat_list.write_text("".join(f"file '{loop}'\n" for _ in range(reps)))
    out = project / "renders" / f"{args.project}.mp4"
    print(f"[channel] Muxing final video ({fmt_ts(audio_dur, True)}, loop x{reps})…")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
         "-f", "concat", "-safe", "0", "-i", str(concat_list), "-i", str(mix),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
         "-t", f"{audio_dur:.3f}", "-movflags", "+faststart", str(out)])

    # 4) Artifacts
    (project / "artifacts" / "chapters.txt").write_text("\n".join(chapters) + "\n")
    (project / "artifacts" / "tracklist.json").write_text(json.dumps({
        "output": str(out), "duration": probe_duration(out), "gap": gap, "crossfade": xf,
        "order_mode": args.order, "seed": args.seed, "clips": [str(c) for c in clips],
        "tracks": [{"start": round(s, 3), "timestamp": fmt_ts(s, force_h), "title": t["title"],
                    "slug": t["slug"], "duration": t["duration"]} for s, t in zip(starts, ordered)],
    }, indent=2, ensure_ascii=False))
    print(f"[channel] Done: {out}\n[channel] Chapters: {project / 'artifacts' / 'chapters.txt'}")


if __name__ == "__main__":
    main()
