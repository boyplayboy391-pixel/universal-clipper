#!/usr/bin/env python3
"""Viral karaoke captions: build .ass from word timestamps and burn into a 1080x1920 clip."""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path
import pysubs2

GOLD_ASS = r"{\c&H00D7FF&}"      # #FFD700 in ASS BGR order
WHITE_ASS = r"{\c&H00FFFFFF&}"


def collect_words(transcript, start, end):
    words = []
    for seg in transcript["segments"]:
        for w in seg["words"]:
            if w["end"] > start and w["start"] < end:
                words.append({"w": w["word"], "s": max(0.0, w["start"] - start), "e": min(end, w["end"]) - start})
    return words


def phrases(words, max_words=4, max_gap=0.6):
    cur, out = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > max_gap):
            out.append(cur); cur = []
        cur.append(w)
        if w["w"].rstrip().endswith((".", "?", "!", "।")) and len(cur) >= 2:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def build_ass(words, path, font="Arial Black", size=84, upper=True):
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"], subs.info["PlayResY"] = "1080", "1920"
    subs.info["WrapStyle"] = "0"
    st = pysubs2.SSAStyle(
        fontname=font, fontsize=size, bold=True,
        primarycolor=pysubs2.Color(255, 255, 255), outlinecolor=pysubs2.Color(0, 0, 0),
        backcolor=pysubs2.Color(0, 0, 0, 140), outline=7, shadow=4,
        alignment=2, marginl=70, marginr=70, marginv=280, borderstyle=1)
    subs.styles["Default"] = st
    for ph in phrases(words):
        texts = [(w["w"].upper() if upper else w["w"]) for w in ph]
        for i, w in enumerate(ph):
            end = ph[i + 1]["s"] if i + 1 < len(ph) else w["e"]
            end = max(end, w["s"] + 0.08)
            parts = [(GOLD_ASS if j == i else WHITE_ASS) + t for j, t in enumerate(texts)]
            subs.events.append(pysubs2.SSAEvent(start=int(w["s"] * 1000), end=int(end * 1000), text=" ".join(parts)))
    subs.save(str(path))


def burn(video, ass, out, fps=None, fontsdir=None):
    """Burn .ass into video. Runs ffmpeg inside the ass folder so Windows drive-letter paths can't break the filter."""
    work = Path(tempfile.mkdtemp(prefix="cap_"))
    shutil.copy(ass, work / "captions.ass")
    vf = "ass=captions.ass" + (f":fontsdir={fontsdir}" if fontsdir else "")
    if fps:
        vf += f",fps={fps}"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(Path(video).resolve()),
           "-vf", vf, "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(Path(out).resolve())]
    r = subprocess.run(cmd, cwd=work)
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode != 0:
        sys.exit("[captions] ffmpeg burn failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="1080x1920 clip from smart_crop.py")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--start", type=float, required=True, help="clip start in SOURCE time (to offset words)")
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default="Arial Black")
    ap.add_argument("--fontsdir", default=None)
    ap.add_argument("--fps", type=int, choices=[30, 60], default=30)
    ap.add_argument("--no-upper", action="store_true")
    a = ap.parse_args()
    tr = json.loads(Path(a.transcript).read_text(encoding="utf-8"))
    words = collect_words(tr, a.start, a.end)
    ass = Path(a.out).with_suffix(".ass")
    build_ass(words, ass, font=a.font, upper=not a.no_upper)
    burn(a.video, ass, a.out, fps=a.fps, fontsdir=a.fontsdir)
    ass.unlink(missing_ok=True)
    print(f"[captions] {len(words)} words burned -> {a.out}")


if __name__ == "__main__":
    main()
