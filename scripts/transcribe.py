#!/usr/bin/env python3
"""faster-whisper transcription with word timestamps -> JSON (+ compact .txt for viral scoring)."""
import argparse, json
from pathlib import Path
from common import TEMP


def pick_device():
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", default=str(TEMP / "source.mp4"))
    ap.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium"])
    ap.add_argument("--language", default=None, help="en / hi / omit for auto-detect (Hinglish: try hi or auto)")
    ap.add_argument("--out", default=str(TEMP / "transcript.json"))
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    device, compute = pick_device()
    print(f"[transcribe] model={a.model} device={device} compute={compute}", flush=True)
    try:
        model = WhisperModel(a.model, device=device, compute_type=compute)
    except Exception as e:
        print(f"[transcribe] {device} failed ({e}); falling back to CPU int8")
        model = WhisperModel(a.model, device="cpu", compute_type="int8")

    segs, info = model.transcribe(a.video, word_timestamps=True, language=a.language,
                                  vad_filter=True, beam_size=5, condition_on_previous_text=False)
    out = {"language": info.language, "duration": info.duration, "segments": []}
    lines = []
    for s in segs:
        words = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                 for w in (s.words or []) if w.word.strip()]
        out["segments"].append({"id": s.id, "start": round(s.start, 3), "end": round(s.end, 3),
                                "text": s.text.strip(), "words": words})
        lines.append(f"[{s.start:8.2f}-{s.end:8.2f}] {s.text.strip()}")
        print(lines[-1], flush=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(a.out).with_suffix(".txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"[transcribe] lang={info.language} segments={len(out['segments'])} -> {a.out}")


if __name__ == "__main__":
    main()
