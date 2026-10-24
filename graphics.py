"""Dedicated graphics engine: HTML/CSS templates rendered through a real browser
engine (Chromium via Playwright) so Bangla text shaping (ligatures, vowel signs,
conjuncts), gradients and flexbox layout are all correct — not hand-placed pixels.
"""
import base64
import html
import io
import json
import os
import re
import time
import uuid
from pathlib import Path

import qrcode
from PIL import Image
from playwright.sync_api import sync_playwright

DATA_DIR = Path(os.environ.get("SHAD_DB_PATH", "/data/shad.db")).parent
GFX_DIR = DATA_DIR / "graphics"
GFX_DIR.mkdir(parents=True, exist_ok=True)

MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_FIELD_LEN = 200

BRANDS = {
    "bpda": {"name": "BPDA", "primary": "#0d6e6e", "accent": "#d4af37", "bg1": "#0a4d4d", "bg2": "#0d6e6e"},
    "lenden": {"name": "Lenden", "primary": "#007850", "accent": "#08A870", "bg1": "#064d33", "bg2": "#007850"},
}

FONT_CSS = """
@font-face { font-family: 'Noto Sans Bengali'; src: local('Noto Sans Bengali'); }
@font-face { font-family: 'Noto Sans'; src: local('Noto Sans'); }
* { font-family: 'Noto Sans Bengali', 'Noto Sans', sans-serif; box-sizing: border-box; margin: 0; padding: 0; }
"""


def _esc(s: str) -> str:
    return html.escape(str(s or ""))[:MAX_FIELD_LEN]


def _clean_photo_data_uri(b64_data: str) -> str:
    """Validate + re-encode an uploaded photo (strips EXIF/metadata, normalizes format)."""
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    raw = base64.b64decode(b64_data, validate=True)
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValueError("photo too large (max 8MB)")
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _qr_data_uri(data: str) -> str:
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _render(html_body: str, width: int, height: int) -> bytes:
    page_html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>{FONT_CSS}
html,body {{ width:{width}px; height:{height}px; overflow:hidden; }}
</style></head><body>{html_body}</body></html>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
        page.set_content(page_html, wait_until="networkidle")
        png = page.screenshot(type="png")
        browser.close()
    return png


# ------------------------------------------------------------------ templates

def banner_html(brand: dict, app_name: str, tagline: str, cta: str, screenshot_uri: str | None) -> str:
    shot = f'<img src="{screenshot_uri}" style="width:620px;height:1240px;object-fit:cover;' \
           f'border-radius:28px;box-shadow:0 30px 80px rgba(0,0,0,.5);border:8px solid rgba(255,255,255,.15)">' \
           if screenshot_uri else ""
    return f"""
<div style="width:1080px;height:1920px;background:linear-gradient(160deg,{brand['bg1']},{brand['bg2']} 60%,#000 140%);
display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;overflow:hidden">
  <div style="position:absolute;top:-180px;right:-180px;width:500px;height:500px;border-radius:50%;
    background:radial-gradient(circle,{brand['accent']}55,transparent 70%)"></div>
  <div style="position:absolute;bottom:-220px;left:-160px;width:560px;height:560px;border-radius:50%;
    background:radial-gradient(circle,{brand['accent']}33,transparent 70%)"></div>
  <div style="z-index:1;color:#fff;font-size:56px;font-weight:800;letter-spacing:-1px;margin-bottom:6px;
    text-shadow:0 4px 24px rgba(0,0,0,.4)">{_esc(app_name)}</div>
  <div style="z-index:1;color:{brand['accent']};font-size:28px;font-weight:600;margin-bottom:48px;
    text-align:center;max-width:820px;line-height:1.4">{_esc(tagline)}</div>
  <div style="z-index:1">{shot}</div>
  <div style="z-index:1;margin-top:48px;background:{brand['accent']};color:#04120c;font-weight:800;
    font-size:30px;padding:18px 48px;border-radius:40px;box-shadow:0 12px 32px rgba(0,0,0,.35)">{_esc(cta)}</div>
</div>"""


def poster_html(brand: dict, doctor_name: str, designation: str, specialty: str, phone: str,
                 address: str, photo_uri: str | None) -> str:
    photo = f'<img src="{photo_uri}" style="width:320px;height:320px;border-radius:50%;object-fit:cover;' \
            f'border:8px solid #fff;box-shadow:0 20px 50px rgba(0,0,0,.35)">' \
            if photo_uri else '<div style="width:320px;height:320px;border-radius:50%;background:#eee;' \
            'border:8px solid #fff;box-shadow:0 20px 50px rgba(0,0,0,.35)"></div>'
    return f"""
<div style="width:1080px;height:1350px;background:linear-gradient(180deg,#f5f9f8,#fff 45%);
display:flex;flex-direction:column;align-items:center;position:relative;overflow:hidden">
  <div style="width:100%;height:420px;background:linear-gradient(135deg,{brand['bg1']},{brand['bg2']});
    display:flex;align-items:center;justify-content:center;position:relative">
    <div style="position:absolute;inset:0;background:radial-gradient(circle at 80% 20%,{brand['accent']}44,transparent 60%)"></div>
  </div>
  <div style="margin-top:-170px;z-index:1">{photo}</div>
  <div style="margin-top:28px;font-size:44px;font-weight:800;color:#13201d">{_esc(doctor_name)}</div>
  <div style="margin-top:6px;font-size:26px;font-weight:600;color:{brand['primary']}">{_esc(designation)}</div>
  <div style="margin-top:4px;font-size:22px;color:#6b7b77">{_esc(specialty)}</div>
  <div style="margin-top:44px;width:860px;background:#fff;border-radius:20px;box-shadow:0 10px 40px rgba(0,0,0,.08);
    border:1px solid #eef3f1;padding:28px 36px;display:flex;flex-direction:column;gap:14px">
    <div style="display:flex;align-items:center;gap:14px;font-size:24px;color:#13201d">
      <span style="color:{brand['primary']};font-weight:800">☎</span> {_esc(phone)}</div>
    <div style="display:flex;align-items:center;gap:14px;font-size:24px;color:#13201d">
      <span style="color:{brand['primary']};font-weight:800">⚑</span> {_esc(address)}</div>
  </div>
  <div style="margin-top:auto;margin-bottom:36px;color:{brand['primary']};font-weight:800;font-size:22px">{brand['name']}</div>
</div>"""


def idcard_html(brand: dict, name: str, designation: str, id_number: str, org: str,
                 photo_uri: str | None, qr_data: str) -> str:
    photo = f'<img src="{photo_uri}" style="width:220px;height:260px;border-radius:14px;object-fit:cover;' \
            f'border:4px solid #fff;box-shadow:0 10px 24px rgba(0,0,0,.25)">' \
            if photo_uri else '<div style="width:220px;height:260px;border-radius:14px;background:#e8efed;' \
            'border:4px solid #fff"></div>'
    qr = f'<img src="{_qr_data_uri(qr_data)}" style="width:140px;height:140px;border-radius:10px;background:#fff;padding:8px">'
    return f"""
<div style="width:1276px;height:810px;background:#fff;border-radius:28px;overflow:hidden;
  box-shadow:0 20px 60px rgba(0,0,0,.18);display:flex;flex-direction:column;position:relative">
  <div style="height:170px;background:linear-gradient(120deg,{brand['bg1']},{brand['bg2']});
    display:flex;align-items:center;padding:0 48px;position:relative">
    <div style="position:absolute;inset:0;background:radial-gradient(circle at 90% 0%,{brand['accent']}55,transparent 55%)"></div>
    <div style="z-index:1;color:#fff;font-size:34px;font-weight:800">{_esc(org)}</div>
    <div style="z-index:1;margin-left:auto;color:{brand['accent']};font-size:18px;font-weight:700;
      letter-spacing:2px">IDENTITY CARD</div>
  </div>
  <div style="flex:1;display:flex;align-items:center;padding:40px 48px;gap:40px">
    {photo}
    <div style="flex:1;display:flex;flex-direction:column;gap:10px">
      <div style="font-size:36px;font-weight:800;color:#13201d">{_esc(name)}</div>
      <div style="font-size:22px;font-weight:600;color:{brand['primary']}">{_esc(designation)}</div>
      <div style="font-size:18px;color:#6b7b77;margin-top:10px">ID NO.</div>
      <div style="font-size:26px;font-weight:700;color:#13201d;letter-spacing:1px">{_esc(id_number)}</div>
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:8px">
      {qr}
      <div style="font-size:12px;color:#8a9a96">Scan to verify</div>
    </div>
  </div>
  <div style="height:8px;background:linear-gradient(90deg,{brand['primary']},{brand['accent']})"></div>
</div>"""


# ------------------------------------------------------------------ public API

def make(kind: str, brand_key: str, fields: dict, photo_b64: str | None) -> dict:
    if kind not in ("banner", "poster", "idcard"):
        raise ValueError("unknown kind")
    brand = BRANDS.get(brand_key, BRANDS["bpda"])
    photo_uri = _clean_photo_data_uri(photo_b64) if photo_b64 else None

    if kind == "banner":
        body = banner_html(brand, fields.get("app_name", ""), fields.get("tagline", ""),
                            fields.get("cta", "Download Now"), photo_uri)
        width, height = 1080, 1920
    elif kind == "poster":
        body = poster_html(brand, fields.get("doctor_name", ""), fields.get("designation", ""),
                            fields.get("specialty", ""), fields.get("phone", ""), fields.get("address", ""), photo_uri)
        width, height = 1080, 1350
    else:
        body = idcard_html(brand, fields.get("name", ""), fields.get("designation", ""),
                            fields.get("id_number", ""), fields.get("org", brand["name"]),
                            photo_uri, fields.get("qr_data") or fields.get("id_number", ""))
        width, height = 1276, 810

    png = _render(body, width, height)
    gid = uuid.uuid4().hex[:12]
    out_path = GFX_DIR / f"{gid}.png"
    out_path.write_bytes(png)
    meta = {"id": gid, "kind": kind, "brand": brand_key, "created_at": time.time(),
            "label": fields.get("app_name") or fields.get("doctor_name") or fields.get("name") or kind}
    (GFX_DIR / f"{gid}.json").write_text(json.dumps(meta))
    return meta


def get_path(gid: str) -> Path | None:
    if not re.fullmatch(r"[a-f0-9]{12}", gid or ""):
        return None
    p = GFX_DIR / f"{gid}.png"
    return p if p.exists() else None


def recent(limit: int = 60) -> list[dict]:
    items = []
    for jf in sorted(GFX_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            items.append(json.loads(jf.read_text()))
        except Exception:
            continue
    return items


def delete(gid: str) -> bool:
    if not re.fullmatch(r"[a-f0-9]{12}", gid or ""):
        return False
    png, meta = GFX_DIR / f"{gid}.png", GFX_DIR / f"{gid}.json"
    found = png.exists() or meta.exists()
    png.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return found
