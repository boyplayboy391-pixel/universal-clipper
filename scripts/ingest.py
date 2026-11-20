#!/usr/bin/env python3
"""Ingest a local file or URL into ./temp_work/source.mp4 (best video <=1080p + best audio)."""
import argparse, subprocess, sys, time
from pathlib import Path
from common import TEMP, ensure_dirs, run

CLIENTS = ["android,web", "ios,web", "tv,web", "web"]  # rotated on retry to dodge 403 / throttling


def download(url, out):
    base = ["yt-dlp", "--no-playlist", "--no-part", "--retries", "10", "--fragment-retries", "10",
            "--concurrent-fragments", "4",
            "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
            "--merge-output-format", "mp4", "-o", str(out.with_suffix(".%(ext)s"))]
    last = None
    for attempt, client in enumerate(CLIENTS, 1):
        cmd = base + ["--extractor-args", f"youtube:player_client={client}", url]
        print(f"[ingest] attempt {attempt}/{len(CLIENTS)} client={client}", flush=True)
        r = subprocess.run(cmd)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return
        last = r.returncode
        time.sleep(2 * attempt)
    sys.exit(f"[ingest] yt-dlp failed after retries (code {last}). Try `pip install -U yt-dlp`.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="local path or URL")
    ap.add_argument("--out", default=str(TEMP / "source.mp4"))
    a = ap.parse_args()
    ensure_dirs()
    out = Path(a.out)
    if out.exists():
        out.unlink()
    if a.source.startswith(("http://", "https://")):
        download(a.source, out)
    else:
        src = Path(a.source).expanduser()
        if not src.exists():
            sys.exit(f"[ingest] not found: {src}")
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-c:v", "libx264",
             "-crf", "18", "-preset", "veryfast", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    print(f"[ingest] ready: {out}")


if __name__ == "__main__":
    main()
