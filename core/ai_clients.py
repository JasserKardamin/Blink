"""
Clients HTTP minimalistes vers les services d'IA externes.

- Google Gemini (texte multimodal : légendes, hashtags, transcription, prompts)
- Hugging Face Inference (Stable Diffusion, Whisper)

Chaque fonction lève `AIUnavailable` si le service n'est pas configuré ou
répond en erreur : l'appelant bascule alors sur un traitement local.
"""
import base64
import io
import json
import logging
import re

import requests
from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger("blink.ai")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
HF_URL = "https://router.huggingface.co/hf-inference/models/{model}"


class AIUnavailable(Exception):
    """Le service d'IA n'est pas disponible (clé absente, quota, réseau...)."""


def gemini_enabled():
    return bool(settings.GEMINI_API_KEY)


def hf_enabled():
    return bool(settings.HF_TOKEN)


def image_to_jpeg_bytes(file_or_image, max_side=1024):
    """Ouvre une image (fichier Django, chemin ou PIL), la redimensionne et renvoie du JPEG."""
    if isinstance(file_or_image, Image.Image):
        img = file_or_image
    else:
        if hasattr(file_or_image, "open"):
            file_or_image.open("rb")
        if hasattr(file_or_image, "seek"):
            file_or_image.seek(0)
        img = Image.open(file_or_image)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _extract_json(text):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise


def gemini_json(prompt, *, image_bytes=None, audio_bytes=None, audio_mime="audio/webm", temperature=0.9):
    """Appelle Gemini et renvoie la réponse JSON décodée."""
    if not gemini_enabled():
        raise AIUnavailable("GEMINI_API_KEY non configurée")
    parts = []
    if image_bytes:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}})
    if audio_bytes:
        parts.append({"inline_data": {"mime_type": audio_mime, "data": base64.b64encode(audio_bytes).decode()}})
    parts.append({"text": prompt})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }
    try:
        resp = requests.post(
            GEMINI_URL.format(model=settings.GEMINI_MODEL),
            headers={"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"},
            json=body,
            timeout=settings.AI_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AIUnavailable(f"Gemini injoignable : {exc}") from exc
    if resp.status_code != 200:
        logger.warning("Gemini %s : %s", resp.status_code, resp.text[:300])
        raise AIUnavailable(f"Gemini a répondu {resp.status_code}")
    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(text)
    except (KeyError, IndexError, ValueError) as exc:
        raise AIUnavailable("Réponse Gemini illisible") from exc


def hf_text_to_image(prompt, negative_prompt="blurry, low quality, deformed, text, watermark"):
    """Génère une image avec Stable Diffusion (Hugging Face Inference). Retourne une image PIL."""
    if not hf_enabled():
        raise AIUnavailable("HF_TOKEN non configuré")
    try:
        resp = requests.post(
            HF_URL.format(model=settings.HF_IMAGE_MODEL),
            headers={"Authorization": f"Bearer {settings.HF_TOKEN}", "Accept": "image/png"},
            json={"inputs": prompt, "parameters": {"negative_prompt": negative_prompt}},
            timeout=settings.AI_TIMEOUT * 2,
        )
    except requests.RequestException as exc:
        raise AIUnavailable(f"Hugging Face injoignable : {exc}") from exc
    if resp.status_code != 200 or not resp.headers.get("content-type", "").startswith("image/"):
        logger.warning("HF image %s : %s", resp.status_code, resp.text[:300])
        raise AIUnavailable(f"Hugging Face a répondu {resp.status_code}")
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def hf_whisper(audio_bytes, mime="audio/webm"):
    """Transcrit un audio avec Whisper (Hugging Face Inference). Retourne le texte."""
    if not hf_enabled():
        raise AIUnavailable("HF_TOKEN non configuré")
    try:
        resp = requests.post(
            HF_URL.format(model=settings.HF_WHISPER_MODEL),
            headers={"Authorization": f"Bearer {settings.HF_TOKEN}", "Content-Type": mime},
            data=audio_bytes,
            timeout=settings.AI_TIMEOUT * 2,
        )
    except requests.RequestException as exc:
        raise AIUnavailable(f"Hugging Face injoignable : {exc}") from exc
    if resp.status_code != 200:
        logger.warning("HF whisper %s : %s", resp.status_code, resp.text[:300])
        raise AIUnavailable(f"Whisper a répondu {resp.status_code}")
    try:
        return resp.json()["text"].strip()
    except (KeyError, ValueError) as exc:
        raise AIUnavailable("Réponse Whisper illisible") from exc
