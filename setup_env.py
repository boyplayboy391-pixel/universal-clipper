#!/usr/bin/env python3
"""Phase 1: silent, cross-platform provisioning. Run with any Python 3.10+:  python setup_env.py"""
import os, platform, shutil, subprocess, sys, venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
OS = platform.system()  # Windows / Darwin / Linux


def sh(cmd, check=False):
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check).returncode == 0


def pkg_manager():
    for name in {"Windows": ["winget", "choco"], "Darwin": ["brew"], "Linux": ["apt-get"]}[OS]:
        if shutil.which(name):
            return name
    return None


PKG = {  # tool -> {manager: package id}
    "python": {"winget": "Python.Python.3.12", "choco": "python", "brew": "python@3.12", "apt-get": "python3 python3-venv python3-pip"},
    "ffmpeg": {"winget": "Gyan.FFmpeg", "choco": "ffmpeg", "brew": "ffmpeg", "apt-get": "ffmpeg"},
    "node": {"winget": "OpenJS.NodeJS.LTS", "choco": "nodejs-lts", "brew": "node", "apt-get": "nodejs npm"},
}


def install(tool, pm):
    pid = PKG[tool][pm]
    if pm == "winget":
        return sh(["winget", "install", "-e", "--id", pid, "--silent", "--accept-package-agreements", "--accept-source-agreements"])
    if pm == "choco":
        return sh(["choco", "install", pid, "-y", "--no-progress"])
    if pm == "brew":
        return sh(["brew", "install", pid])
    sudo = [] if hasattr(os, "geteuid") and os.geteuid() == 0 else ["sudo", "-n"]
    return sh(sudo + ["apt-get", "install", "-y", "-qq"] + pid.split())


def ffmpeg_has_ass():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        return " ass " in out and " subtitles " in out
    except FileNotFoundError:
        return False


def main():
    print(f"[setup] OS={OS} python={sys.version.split()[0]}")
    pm = pkg_manager()
    print(f"[setup] package manager: {pm}")
    need = []
    if sys.version_info < (3, 10): need.append("python")
    if not shutil.which("ffmpeg") or not ffmpeg_has_ass(): need.append("ffmpeg")
    if not shutil.which("node"): need.append("node")
    if need and not pm:
        sys.exit(f"[setup] missing {need} and no package manager found; install manually")
    for t in need:
        print(f"[setup] installing {t}")
        install(t, pm)
    if OS == "Windows" and need:
        print("[setup] NOTE: PATH changes need a NEW terminal. If checks below fail, reopen the terminal and rerun.")

    if not VENV.exists():
        print("[setup] creating .venv")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    py = VENV / ("Scripts/python.exe" if OS == "Windows" else "bin/python")
    sh([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip", "wheel"])
    if not sh([str(py), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")]):
        sys.exit("[setup] pip install failed; see error above")
    sh([str(py), "-c", "import sys; sys.path.insert(0,'scripts'); import smart_crop; print('  YuNet model:', smart_crop.ensure_yunet())"])

    for d in ("temp_work", "final_clips", "scripts", ".agent/skills/universal-clipper"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    print("\n[verify]")
    ok = True
    for tool in ("ffmpeg", "yt-dlp", "node"):
        path = shutil.which(tool) or (str(VENV / ("Scripts" if OS == "Windows" else "bin") / tool) if tool == "yt-dlp" else None)
        ver = ""
        if path:
            try:
                ver = subprocess.run([path, "-version" if tool == "ffmpeg" else "--version"], capture_output=True, text=True).stdout.splitlines()[0]
            except Exception: pass
        print(f"  {tool:8} {'OK ' + ver if path else 'MISSING'}"); ok &= bool(path)
    a = ffmpeg_has_ass()
    print(f"  ffmpeg ass+subtitles filters: {'OK' if a else 'MISSING'}"); ok &= a
    code = ("import faster_whisper, cv2, numpy, pysubs2, ctranslate2;"
            "print('  faster-whisper', faster_whisper.__version__, '| cv2', cv2.__version__, '| numpy', numpy.__version__);"
            "print('  CUDA devices:', ctranslate2.get_cuda_device_count(), '(0 => CPU int8)')")
    ok &= subprocess.run([str(py), "-c", code]).returncode == 0
    print(f"\n[setup] venv: {VENV}\n[setup] {'ALL GOOD' if ok else 'INCOMPLETE - see above'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
