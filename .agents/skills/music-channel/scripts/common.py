"""Shared helpers for music channel scripts.

All paths are resolved relative to the repository root so the scripts can be
run from anywhere. Outputs always go under ``projects/`` (gitignored), per the
workspace contract. Configurable for any music genre or channel fork.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

# .agents/skills/music-channel/scripts/common.py -> repo root is parents[4]
REPO = Path(__file__).resolve().parents[4]
SONGS_DIR = REPO / "project-assets" / "songs"
VIDEOS_DIR = REPO / "project-assets" / "videos"
PROJECTS = REPO / "projects"

MASTERS_PROJECT = PROJECTS / "audio-masters"
MASTERS_DIR = MASTERS_PROJECT / "assets" / "audio"
MASTERS_MANIFEST = MASTERS_PROJECT / "artifacts" / "masters.json"

# Load .env if present
env_file = REPO / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k not in os.environ:
                os.environ[k] = v

CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "Music Channel")

# Example: "Artist - Title - [@tag]" or "Artist - Title"
FILENAME_RE = re.compile(r"^(?P<artist>.+?) - (?P<title>.+?)(?: - \[@(?P<tag>[^\]]+)\])?$")

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def require_ffmpeg() -> None:
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    if missing:
        sys.exit(
            f"[channel] Missing binaries: {', '.join(missing)}. "
            "Install with: sudo apt update && sudo apt install -y ffmpeg"
        )


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "untitled"


def parse_song_filename(path: Path) -> dict:
    m = FILENAME_RE.match(path.stem)
    if not m:
        return {"artist": None, "title": path.stem, "tag": None, "slug": slugify(path.stem)}
    title = m.group("title").strip()
    tag = m.group("tag").strip() if m.group("tag") else None
    return {
        "artist": m.group("artist").strip(),
        "title": title,
        "tag": tag,
        "slug": slugify(title),
    }


def run(cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)


def probe_duration(path: Path) -> float:
    out = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture=True,
    ).stdout.strip()
    return float(out)


def tail_rms_db(path: Path, window: float = 0.5) -> float:
    """RMS level (dBFS) of the last ``window`` seconds. High value = abrupt ending."""
    proc = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-sseof", f"-{window}", "-i", str(path),
         "-af", "astats=measure_perchannel=none", "-f", "null", "-"],
        capture=True,
    )
    levels = re.findall(r"RMS level dB:\s*(-?inf|-?[\d.]+)", proc.stderr)
    if not levels:
        return float("-inf")
    val = levels[-1]
    return float("-inf") if "inf" in val else float(val)


def measure_loudness(path: Path, lufs: float = -14.0, tp: float = -1.0, lra: float = 11.0,
                     extra_filters: str = "") -> dict:
    """First pass of two-pass loudnorm. Returns ffmpeg's JSON measurement dict."""
    chain = f"{extra_filters + ',' if extra_filters else ''}loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json"
    proc = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", chain, "-f", "null", "-"],
        capture=True,
    )
    start = proc.stderr.rfind("{")
    end = proc.stderr.rfind("}")
    return json.loads(proc.stderr[start:end + 1])


def fmt_ts(seconds: float, force_hours: bool = False) -> str:
    """YouTube chapter timestamp: M:SS / MM:SS, or H:MM:SS when needed."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h or force_hours:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def find_font() -> str | None:
    """Return a bold sans font file for drawtext, or None."""
    if shutil.which("fc-match"):
        try:
            f = run(["fc-match", "-f", "%{file}", "DejaVu Sans:bold"], capture=True).stdout.strip()
            if f and Path(f).exists():
                return f
        except subprocess.CalledProcessError:
            pass
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        if Path(cand).exists():
            return cand
    return None


def load_masters() -> list[dict]:
    if not MASTERS_MANIFEST.exists():
        sys.exit(f"[channel] {MASTERS_MANIFEST} not found. Run master_tracks.py first.")
    return json.loads(MASTERS_MANIFEST.read_text())["tracks"]


def resolve_master(key: str) -> dict:
    """Find a mastered track by slug, title (case-insensitive) or path."""
    tracks = load_masters()
    k = key.lower()
    for t in tracks:
        if k in (t["slug"], t["title"].lower()) or Path(key).resolve() == Path(t["master"]).resolve():
            return t
    matches = [t for t in tracks if k in t["slug"] or k in t["title"].lower()]
    if len(matches) == 1:
        return matches[0]
    sys.exit(f"[channel] Could not uniquely resolve track '{key}'. Candidates: "
             f"{[t['slug'] for t in matches] or 'none'}")


def blur_pad_filter(w: int, h: int, fps: int, inp: str = "0:v", out: str = "v", n: str = "") -> str:
    """Fit any aspect ratio into WxH: sharp foreground over blurred, cropped background."""
    return (
        f"[{inp}]split[bgsrc{n}][fgsrc{n}];"
        f"[bgsrc{n}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:2[bg{n}];"
        f"[fgsrc{n}]scale={w}:{h}:force_original_aspect_ratio=decrease[fg{n}];"
        f"[bg{n}][fg{n}]overlay=(W-w)/2:(H-h)/2,fps={fps},setsar=1,format=yuv420p[{out}]"
    )


def build_visual_loop(clips: list[Path], out: Path, w: int, h: int, fps: int,
                      clip_seconds: float | None = None, image_seconds: float = 6.0,
                      crf: int = 18, preset: str = "medium") -> float:
    """Normalize clips/images to one silent H.264 loop file. Returns its duration.

    Every segment starts on a keyframe and the GOP is fixed (2 s) so the result
    can be safely repeated with the concat demuxer + ``-c copy``.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    for c in clips:
        if c.suffix.lower() in IMAGE_EXTS:
            cmd += ["-loop", "1", "-t", str(image_seconds), "-i", str(c)]
        elif clip_seconds:
            cmd += ["-t", str(clip_seconds), "-i", str(c)]
        else:
            cmd += ["-i", str(c)]
    parts = [blur_pad_filter(w, h, fps, inp=f"{i}:v", out=f"v{i}", n=str(i))
             for i in range(len(clips))]
    concat_in = "".join(f"[v{i}]" for i in range(len(clips)))
    parts.append(f"{concat_in}concat=n={len(clips)}:v=1:a=0[vout]")
    gop = fps * 2
    cmd += [
        "-filter_complex", ";".join(parts), "-map", "[vout]", "-an",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-r", str(fps), "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        "-movflags", "+faststart", str(out),
    ]
    run(cmd)
    return probe_duration(out)


def collect_clips(paths: list[str] | None) -> list[Path]:
    if paths:
        clips = [Path(p).expanduser().resolve() for p in paths]
    else:
        clips = sorted(p for p in VIDEOS_DIR.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    missing = [str(c) for c in clips if not c.exists()]
    if missing:
        sys.exit(f"[channel] Clips not found: {missing}")
    if not clips:
        sys.exit("[channel] No clips provided/found.")
    return clips
