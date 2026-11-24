# -*- coding: utf-8 -*-
"""Piece photos: validate, orient, resize, gentle clarity, small corner watermark. Uploads from PC or phone."""
import base64
import io
import os
import re
import secrets
import time

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from core import GoldError

MAX_EDGE = 1600


def enhance(im):
    """Gentle: a touch of contrast, warmth-safe saturation and clarity. Never changes the piece's look."""
    im = ImageOps.exif_transpose(im).convert("RGB")
    if max(im.size) > MAX_EDGE:
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.06)
    im = ImageEnhance.Color(im).enhance(1.05)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=55, threshold=2))
    return im


def watermark(im, logo_path, rel=0.11, opacity=0.6):
    """Small logo in the bottom-left corner, away from the piece."""
    if not logo_path or not os.path.exists(logo_path):
        return im
    logo = Image.open(logo_path).convert("RGBA")
    w = max(48, int(im.width * rel))
    logo = logo.resize((w, int(logo.height * w / logo.width)), Image.LANCZOS)
    a = logo.split()[3].point(lambda v: int(v * opacity))
    logo.putalpha(a)
    m = int(im.width * 0.025)
    base = im.convert("RGBA")
    base.alpha_composite(logo, (m, base.height - logo.height - m))
    return base.convert("RGB")


def save_piece_photo(data_url, folder, logo_path=None, crop=None, enhance_it=True):
    m = re.match(r"data:image/(jpeg|jpg|png|webp|heic);base64,(.+)$", data_url or "", re.S)
    if not m:
        raise GoldError("الصورة لازم تكون JPG أو PNG")
    blob = base64.b64decode(m.group(2), validate=False)
    if len(blob) > 15_000_000:
        raise GoldError("الصورة كبيرة جداً")
    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
    except Exception:
        raise GoldError("ملف الصورة غير صالح")
    return save_image(im, folder, logo_path, crop, enhance_it)


def save_image(im, folder, logo_path=None, crop=None, enhance_it=True):
    if enhance_it:
        im = enhance(im)
    else:                                    # already processed at the branch: keep it as it is
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > MAX_EDGE:
            im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    if crop:
        im = im.crop(crop)
    im = watermark(im, logo_path)
    name = f"{int(time.time())}_{secrets.token_hex(5)}.jpg"
    os.makedirs(folder, exist_ok=True)
    im.save(os.path.join(folder, name), "JPEG", quality=86, optimize=True, progressive=True)
    return name
