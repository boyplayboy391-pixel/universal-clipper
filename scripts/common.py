"""Shared helpers for the universal-clipper pipeline."""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMP = ROOT / "temp_work"
FINAL = ROOT / "final_clips"


def run(cmd, **kw):
    kw.setdefault("check", True)
    return subprocess.run([str(c) for c in cmd], **kw)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def duration(path):
    return float(probe(path)["format"]["duration"])


def video_info(path):
    s = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den or 1)


def ensure_dirs():
    for d in (TEMP, FINAL):
        d.mkdir(parents=True, exist_ok=True)
