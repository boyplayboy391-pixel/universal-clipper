#!/usr/bin/env python3
"""Subject-tracking 9:16 reframe with EMA smoothing and blurred-background pillarbox fallback.

Reads [start,end) of the source, writes a 1080x1920 H.264 clip (with audio) to --out.
Face/subject found  -> smooth 9:16 crop that pans on an EMA-filtered face centre.
No subject > 1.5 s  -> cross-fades to a 1080x1920 blurred-background pillarbox layout.
"""
import argparse, subprocess, sys, urllib.request
from pathlib import Path
import cv2
import numpy as np
from common import video_info

W, H = 1080, 1920
LOST_SECONDS = 1.5      # no-subject time before switching to pillarbox
EMA_ALPHA = 0.12        # lower = smoother pan
DETECT_EVERY = 3        # run detector every N frames
FADE_SECONDS = 0.35


YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_PATH = Path(__file__).resolve().parent.parent / "models" / "yunet.onnx"


def ensure_yunet():
    """Download the tiny YuNet face model once (~230 KB). Returns path or None."""
    try:
        if YUNET_PATH.exists() and YUNET_PATH.stat().st_size > 100_000:
            return YUNET_PATH
        YUNET_PATH.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
        if YUNET_PATH.stat().st_size > 100_000:
            return YUNET_PATH
        YUNET_PATH.unlink(missing_ok=True)
    except Exception as e:
        print(f"[crop] YuNet download failed: {e}", flush=True)
    return None


class Detector:
    """OpenCV YuNet face detector (no mediapipe), Haar fallback. Returns (cx_norm, width_norm) or None."""
    def __init__(self):
        self.yn = None
        self.size = None
        m = ensure_yunet()
        if m is not None and hasattr(cv2, "FaceDetectorYN"):
            try:
                self.yn = cv2.FaceDetectorYN.create(str(m), "", (480, 270), 0.6, 0.3, 20)
                print("[crop] detector: YuNet", flush=True)
            except Exception as e:
                print(f"[crop] YuNet init failed: {e}", flush=True)
        self.haar = None
        if self.yn is None:
            try:
                self.haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
                print("[crop] detector: OpenCV Haar (weaker)", flush=True)
            except Exception as e:
                print(f"[crop] no face detector available ({e}); pillarbox only", flush=True)

    def __call__(self, bgr):
        h, w = bgr.shape[:2]
        sw = 480
        sm = cv2.resize(bgr, (sw, max(2, int(h * sw / w))))
        if self.yn is not None:
            if self.size != sm.shape[:2]:
                self.yn.setInputSize((sm.shape[1], sm.shape[0])); self.size = sm.shape[:2]
            _, faces = self.yn.detect(sm)
            if faces is None or len(faces) == 0:
                return None
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])[:4]
            return (x + fw / 2) / sm.shape[1], fw / sm.shape[1]
        if self.haar is None:
            return None
        faces = self.haar.detectMultiScale(cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY), 1.15, 5, minSize=(40, 40))
        if len(faces) == 0:
            return None
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        return (x + fw / 2) / sm.shape[1], fw / sm.shape[1]


def pillarbox(frame):
    h, w = frame.shape[:2]
    # blurred cover background (blur on a tiny copy for speed)
    scale = max(W / w, H / h)
    bw, bh = int(w * scale), int(h * scale)
    tiny = cv2.resize(frame, (max(16, bw // 12), max(16, bh // 12)))
    tiny = cv2.GaussianBlur(tiny, (0, 0), 6)
    bg = cv2.resize(tiny, (bw, bh), interpolation=cv2.INTER_LINEAR)
    x0, y0 = (bw - W) // 2, (bh - H) // 2
    bg = bg[y0:y0 + H, x0:x0 + W]
    bg = (bg * 0.7).astype(np.uint8)
    fh = int(h * W / w)
    fg = cv2.resize(frame, (W, fh), interpolation=cv2.INTER_AREA)
    y = (H - fh) // 2
    out = bg.copy()
    out[y:y + fh] = fg
    return out


def crop_frame(frame, cx_px, cw):
    h, w = frame.shape[:2]
    x0 = int(round(min(max(cx_px - cw / 2, 0), w - cw)))
    c = frame[:, x0:x0 + cw]
    return cv2.resize(c, (W, H), interpolation=cv2.INTER_CUBIC if c.shape[0] < H else cv2.INTER_AREA)


def reframe(src, start, end, out, crf=18):
    w, h, fps = video_info(src)
    cap = cv2.VideoCapture(str(src))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    cw = min(w, int(round(h * 9 / 16 / 2)) * 2)
    n_frames = int((end - start) * fps)

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{fps:.5f}", "-i", "-",
         "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src),
         "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
        stdin=subprocess.PIPE)

    det = Detector()
    cx = w / 2
    ema = None
    last_seen = start
    alpha = 1.0                    # 0 = tracked crop, 1 = pillarbox
    fade_step = 1.0 / max(1, FADE_SECONDS * fps)
    pil_frames = 0
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        t = start + i / fps
        if i % DETECT_EVERY == 0:
            d = det(frame)
            if d is not None:
                cx_n, _ = d
                target = cx_n * w
                ema = target if ema is None else EMA_ALPHA * target + (1 - EMA_ALPHA) * ema
                last_seen = t
        if ema is not None:
            cx = ema
        lost = (t - last_seen) > LOST_SECONDS if ema is not None else (t - start) > LOST_SECONDS
        target_alpha = 1.0 if lost else 0.0
        alpha += max(-fade_step, min(fade_step, target_alpha - alpha))
        if alpha <= 0.0:
            frame_out = crop_frame(frame, cx, cw)
        elif alpha >= 1.0:
            frame_out = pillarbox(frame); pil_frames += 1
        else:
            frame_out = cv2.addWeighted(pillarbox(frame), alpha, crop_frame(frame, cx, cw), 1 - alpha, 0)
        ff.stdin.write(frame_out.tobytes())
    cap.release()
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("[crop] ffmpeg failed")
    print(f"[crop] done: {out} (pillarbox frames: {pil_frames}/{n_frames})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    reframe(a.source, a.start, a.end, a.out)


if __name__ == "__main__":
    main()
