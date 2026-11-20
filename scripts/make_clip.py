#!/usr/bin/env python3
"""One-shot: sentence-snap window -> smart_crop -> karaoke captions -> ./final_clips/clip_NN_slug.mp4"""
import argparse, json, re
from pathlib import Path
from common import TEMP, FINAL, ensure_dirs, video_info
import smart_crop, render_captions


def snap(tr, start, end, max_shift=4.0):
    """Move start/end to the nearest segment (sentence-ish) boundary within max_shift seconds."""
    starts = [s["start"] for s in tr["segments"]]
    ends = [s["end"] for s in tr["segments"]]
    ns = min(starts, key=lambda x: abs(x - start))
    ne = min(ends, key=lambda x: abs(x - end))
    return (ns if abs(ns - start) <= max_shift else start), (ne if abs(ne - end) <= max_shift else end)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(TEMP / "source.mp4"))
    ap.add_argument("--transcript", default=str(TEMP / "transcript.json"))
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--font", default="Arial Black")
    ap.add_argument("--fontsdir", default=None)
    ap.add_argument("--fps", type=int, choices=[30, 60], default=None)
    ap.add_argument("--no-snap", action="store_true")
    a = ap.parse_args()
    ensure_dirs()
    tr = json.loads(Path(a.transcript).read_text(encoding="utf-8"))
    s, e = (a.start, a.end) if a.no_snap else snap(tr, a.start, a.end)
    print(f"[clip] window {a.start:.2f}-{a.end:.2f} -> snapped {s:.2f}-{e:.2f} ({e - s:.1f}s)")
    fps = a.fps or (60 if video_info(a.source)[2] >= 50 else 30)
    slug = re.sub(r"[^a-z0-9]+", "-", a.slug.lower()).strip("-")[:40] or "clip"
    mid = TEMP / f"crop_{a.index:02d}.mp4"
    smart_crop.reframe(a.source, s, e, mid)
    out = FINAL / f"clip_{a.index:02d}_{slug}.mp4"
    words = render_captions.collect_words(tr, s, e)
    ass = TEMP / f"cap_{a.index:02d}.ass"
    render_captions.build_ass(words, ass, font=a.font)
    render_captions.burn(mid, ass, out, fps=fps, fontsdir=a.fontsdir)
    print(f"[clip] exported {out}")


if __name__ == "__main__":
    main()
