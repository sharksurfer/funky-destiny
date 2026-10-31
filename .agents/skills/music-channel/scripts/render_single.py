#!/usr/bin/env python3
"""Render one YouTube video for a single mastered song.

The visual is one or more clips (or images) normalized to 16:9 with a blurred
fill, looped for the full song length, with an animated title card at the start
and a fade in/out. Audio is the mastered FLAC encoded as AAC 320k / 48 kHz.

Writes:
  projects/single-<slug>/assets/video/loop.mp4
  projects/single-<slug>/renders/<slug>.mp4

Examples:
  python3 render_single.py --song track-slug \
      --clips project-assets/videos/clip1.mp4
  python3 render_single.py --song "track title" --clips a.mp4 b.mp4 --no-title
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CHANNEL_NAME, PROJECTS, build_visual_loop, collect_clips,  # noqa: E402
                    find_font, probe_duration, require_ffmpeg, resolve_master, run)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--song", required=True, help="Slug, title or path of a mastered track")
    ap.add_argument("--clips", nargs="+", required=True, help="Video clips and/or images for the visual")
    ap.add_argument("--title", help="On-screen title (default: track title)")
    ap.add_argument("--subtitle", default=CHANNEL_NAME, help="Second line under the title")
    ap.add_argument("--no-title", action="store_true")
    ap.add_argument("--title-seconds", type=float, default=8.0)
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--font", help="Font file for drawtext (default: DejaVu Sans Bold)")
    ap.add_argument("--project", help="Project id (default: single-<slug>)")
    args = ap.parse_args()

    require_ffmpeg()
    track = resolve_master(args.song)
    master = Path(track["master"])
    dur = probe_duration(master)
    w, h = (int(x) for x in args.resolution.lower().split("x"))
    project = PROJECTS / (args.project or f"single-{track['slug']}")
    (project / "renders").mkdir(parents=True, exist_ok=True)
    (project / "artifacts").mkdir(parents=True, exist_ok=True)

    clips = collect_clips(args.clips)
    loop = project / "assets" / "video" / "loop.mp4"
    print(f"[channel] Building visual loop from {len(clips)} clip(s)…")
    loop_dur = build_visual_loop(clips, loop, w, h, args.fps, crf=args.crf, preset=args.preset)

    vf = [f"fade=t=in:st=0:d=1", f"fade=t=out:st={max(dur - 2.5, 0):.3f}:d=2.5"]
    if not args.no_title:
        font = args.font or find_font()
        if not font:
            sys.exit("[channel] No font found for title. Pass --font or use --no-title.")
        ts = args.title_seconds
        alpha = f"'if(lt(t,0.6),t/0.6,if(lt(t,{ts - 1}),1,if(lt(t,{ts}),{ts}-t,0)))'"
        title_file = project / "artifacts" / "title.txt"
        sub_file = project / "artifacts" / "subtitle.txt"
        title_file.write_text(args.title or track["title"])
        sub_file.write_text(args.subtitle or "")
        common = (f"fontfile={font}:fontcolor=white:shadowcolor=black@0.7:shadowx=3:shadowy=3"
                  f":alpha={alpha}:enable='lt(t,{ts})'")
        vf.append(f"drawtext=textfile={title_file}:{common}:fontsize=h/12"
                  f":x=(w-text_w)/2:y=h*0.72")
        if args.subtitle:
            vf.append(f"drawtext=textfile={sub_file}:{common}:fontsize=h/28"
                      f":x=(w-text_w)/2:y=h*0.72+h/12+h/40")

    out = project / "renders" / f"{track['slug']}.mp4"
    gop = args.fps * 2
    print(f"[channel] Rendering {out.name} ({dur:.1f}s)…")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
         "-stream_loop", "-1", "-i", str(loop), "-i", str(master),
         "-filter_complex", f"[0:v]{','.join(vf)}[v]",
         "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
         "-pix_fmt", "yuv420p", "-r", str(args.fps), "-g", str(gop),
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
         "-metadata", f"title={track['title']}", "-movflags", "+faststart", str(out)])

    report = {"track": track, "clips": [str(c) for c in clips], "loop_duration": loop_dur,
              "output": str(out), "duration": probe_duration(out), "resolution": args.resolution,
              "fps": args.fps}
    (project / "artifacts" / "render_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"[channel] Done: {out}")


if __name__ == "__main__":
    main()
