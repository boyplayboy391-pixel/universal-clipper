#!/usr/bin/env python3
"""Verify every clip in ./final_clips (size > 0, valid duration, 1080x1920) then wipe ./temp_work."""
import shutil, sys
from common import FINAL, TEMP, duration, video_info


def main():
    clips = sorted(FINAL.glob("clip_*.mp4"))
    if not clips:
        sys.exit("[finalize] no clips found; temp_work kept")
    bad = []
    for c in clips:
        try:
            d = duration(c); w, h, fps = video_info(c)
            ok = c.stat().st_size > 0 and d > 1 and (w, h) == (1080, 1920)
            print(f"[finalize] {c.name}: {d:.1f}s {w}x{h}@{fps:.0f} {c.stat().st_size/1e6:.1f}MB {'OK' if ok else 'BAD'}")
            if not ok: bad.append(c.name)
        except Exception as e:
            print(f"[finalize] {c.name}: {e}"); bad.append(c.name)
    if bad:
        sys.exit(f"[finalize] verification failed for {bad}; temp_work kept")
    shutil.rmtree(TEMP, ignore_errors=True); TEMP.mkdir(exist_ok=True)
    print("[finalize] temp_work wiped")


if __name__ == "__main__":
    main()
