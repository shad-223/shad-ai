"""Native reel/video generator: script (user-provided) -> TTS (ElevenLabs, via the
vault's active key) -> Ken-Burns image slideshow -> burned-in Bangla-capable
captions synced to real speech timing -> MP4. No stock-footage AI matching (that
stays Studio's job); no Facebook posting (download-only, by design)."""
import base64
import io
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image

import vault

DATA_DIR = Path(os.environ.get("SHAD_DB_PATH", "/data/shad.db")).parent
REEL_DIR = DATA_DIR / "reels"
REEL_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 30
MAX_LINES = 40
MAX_LINE_CHARS = 300
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class RenderError(Exception):
    pass


def _run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RenderError(f"ffmpeg failed: {r.stderr[-2000:]}")


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def _tts_line(text: str, voice_id: str, api_key: str, out_path: Path):
    r = httpx.post(
        ELEVENLABS_TTS_URL.format(voice_id=voice_id),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=60,
    )
    if r.status_code != 200:
        raise RenderError(f"ElevenLabs TTS failed ({r.status_code}): {r.text[:300]}")
    out_path.write_bytes(r.content)


def _srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _save_image(b64_data: str, out_path: Path):
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    raw = base64.b64decode(b64_data, validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise RenderError("image too large (max 10MB)")
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.save(out_path, format="JPEG", quality=92)


def make(lines: list[str], voice_id: str, images_b64: list[str]) -> dict:
    lines = [ln.strip() for ln in lines if ln.strip()][:MAX_LINES]
    if not lines:
        raise RenderError("script is empty")
    for ln in lines:
        if len(ln) > MAX_LINE_CHARS:
            raise RenderError(f"a line exceeds {MAX_LINE_CHARS} characters")
    images_b64 = images_b64[:MAX_IMAGES]
    if not images_b64:
        raise RenderError("at least one image is required")
    voice_id = (voice_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{10,40}", voice_id):
        raise RenderError("voice_id looks invalid — paste it from your ElevenLabs dashboard")

    api_key = vault.get_active_value("elevenlabs")
    if not api_key:
        raise RenderError("no active ElevenLabs key in the vault — add and activate one first")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1) TTS each line, measure real durations
        clip_paths, durations = [], []
        for i, ln in enumerate(lines):
            p = tmp / f"line_{i:03d}.mp3"
            _tts_line(ln, voice_id, api_key, p)
            clip_paths.append(p)
            durations.append(_ffprobe_duration(p))

        # 2) concat audio
        concat_list = tmp / "audio_concat.txt"
        concat_list.write_text("".join(f"file '{p.name}'\n" for p in clip_paths))
        audio_path = tmp / "audio.m4a"
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
              "-c:a", "aac", "-b:a", "160k", str(audio_path)])
        total_duration = sum(durations)

        # 3) SRT synced to real per-line durations
        srt_path = tmp / "captions.srt"
        srt = []
        t = 0.0
        for i, (ln, dur) in enumerate(zip(lines, durations), start=1):
            srt.append(f"{i}\n{_srt_timestamp(t)} --> {_srt_timestamp(t + dur)}\n{ln}\n")
            t += dur
        srt_path.write_text("\n".join(srt), encoding="utf-8")

        # 4) Ken-Burns segment per image, slice duration split evenly across total_duration
        n = len(images_b64)
        slice_dur = total_duration / n
        seg_paths = []
        for i, b64 in enumerate(images_b64):
            img_path = tmp / f"img_{i:03d}.jpg"
            _save_image(b64, img_path)
            seg_path = tmp / f"seg_{i:03d}.mp4"
            frames = max(int(round(slice_dur * FPS)), 1)
            zoom_dir = "min(zoom+0.0015,1.3)" if i % 2 == 0 else "if(eq(on,1),1.3,max(zoom-0.0015,1.0))"
            _run([
                "ffmpeg", "-y", "-i", str(img_path),
                "-vf", f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
                       f"crop={W*2}:{H*2},"
                       f"zoompan=z='{zoom_dir}':d={frames}:s={W}x{H}:fps={FPS}",
                "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
                str(seg_path),
            ])
            seg_paths.append(seg_path)

        # 5) concat video segments
        vconcat_list = tmp / "video_concat.txt"
        vconcat_list.write_text("".join(f"file '{p.name}'\n" for p in seg_paths))
        video_nosub = tmp / "video_nosub.mp4"
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vconcat_list),
              "-c", "copy", str(video_nosub)])

        # 6) mux audio, burn captions in one final encode
        gid = uuid.uuid4().hex[:12]
        out_path = REEL_DIR / f"{gid}.mp4"
        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        _run([
            "ffmpeg", "-y", "-i", str(video_nosub), "-i", str(audio_path),
            "-vf", f"subtitles={srt_escaped}:force_style="
                   f"'FontName=Noto Sans Bengali,FontSize=14,PrimaryColour=&H00FFFFFF,"
                   f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=90'",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out_path),
        ])

    meta = {"id": gid, "kind": "reel", "created_at": time.time(), "duration": round(total_duration, 1),
             "lines": len(lines), "label": lines[0][:40]}
    (REEL_DIR / f"{gid}.json").write_text(json.dumps(meta))
    return meta


def get_path(gid: str) -> Path | None:
    if not re.fullmatch(r"[a-f0-9]{12}", gid or ""):
        return None
    p = REEL_DIR / f"{gid}.mp4"
    return p if p.exists() else None


def recent(limit: int = 60) -> list[dict]:
    items = []
    for jf in sorted(REEL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            items.append(json.loads(jf.read_text()))
        except Exception:
            continue
    return items


def delete(gid: str) -> bool:
    if not re.fullmatch(r"[a-f0-9]{12}", gid or ""):
        return False
    mp4, meta = REEL_DIR / f"{gid}.mp4", REEL_DIR / f"{gid}.json"
    found = mp4.exists() or meta.exists()
    mp4.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return found
