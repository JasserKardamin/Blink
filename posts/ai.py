"""
Génération de légendes stylisées et de hashtags (Gestion 1 – Gemini).

Si Gemini n'est pas configuré ou indisponible, un générateur local analyse
les couleurs de l'image pour produire une légende cohérente : l'application
reste utilisable sans clé d'API.
"""
import colorsys
import hashlib
import random
import re
import unicodedata

from PIL import Image, ImageStat

from core.ai_clients import AIUnavailable, gemini_json, image_to_jpeg_bytes

STYLE_INSTRUCTIONS = {
    "poetique": "poétique, imagée et douce, comme un court vers libre",
    "marketing": "accrocheuse et dynamique, façon community manager, avec un appel à l'action",
    "humoristique": "drôle et légère, avec une touche d'autodérision",
}

PROMPT = """Tu es l'assistant créatif du réseau social Blink.
Analyse la photo et rédige UNE légende en français, {style_desc}, de 1 à 2 phrases (max 220 caractères), avec au plus un emoji.
{context}Propose aussi entre 5 et 8 hashtags pertinents (sans le caractère #, en minuscules, sans espaces ni accents).
Réponds uniquement en JSON : {{"caption": "...", "hashtags": ["...", "..."]}}"""


def slugify_tag(tag):
    tag = unicodedata.normalize("NFKD", str(tag)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9_]", "", tag.lower().lstrip("#"))


def clean_hashtags(tags, limit=10):
    result = []
    for tag in tags or []:
        slug = slugify_tag(tag)
        if slug and slug not in result:
            result.append(slug)
    return result[:limit]


def generate_caption(image_file, style="poetique", context=""):
    """Retourne {caption, hashtags, engine, prompt}."""
    style = style if style in STYLE_INSTRUCTIONS else "poetique"
    image_bytes = image_to_jpeg_bytes(image_file)
    context_line = f"Contexte donné par l'auteur : « {context.strip()[:300]} ».\n" if context and context.strip() else ""
    prompt = PROMPT.format(style_desc=STYLE_INSTRUCTIONS[style], context=context_line)
    try:
        data = gemini_json(prompt, image_bytes=image_bytes)
        caption = str(data.get("caption", "")).strip()
        hashtags = clean_hashtags(data.get("hashtags", []))
        if not caption:
            raise AIUnavailable("Légende vide")
        if "blink" not in hashtags:
            hashtags.append("blink")
        return {"caption": caption, "hashtags": hashtags, "engine": "gemini", "prompt": prompt}
    except AIUnavailable:
        result = local_caption(image_bytes, style)
        result["prompt"] = prompt
        return result


# --- Générateur local --------------------------------------------------------

MOODS = {
    "golden": {
        "words": ["la lumière dorée", "ce soleil couchant", "l'heure dorée"],
        "tags": ["goldenhour", "sunset", "coucherdesoleil", "lumiere"],
    },
    "blue": {
        "words": ["ce bleu infini", "le ciel et la mer", "cette brise bleue"],
        "tags": ["bleu", "ciel", "mer", "evasion"],
    },
    "green": {
        "words": ["la nature", "ce vert apaisant", "les feuilles qui respirent"],
        "tags": ["nature", "green", "outdoor", "respirer"],
    },
    "pink": {
        "words": ["ces tons pastel", "la douceur rose", "ce rêve pastel"],
        "tags": ["pastel", "pink", "douceur", "aesthetic"],
    },
    "night": {
        "words": ["la nuit", "les ombres", "ce moment nocturne"],
        "tags": ["nuit", "nightvibes", "moody", "citylights"],
    },
    "bright": {
        "words": ["cette lumière", "la clarté du jour", "ce moment lumineux"],
        "tags": ["lumineux", "daylight", "goodvibes", "instant"],
    },
    "neutral": {
        "words": ["ce moment", "cet instant", "ce souvenir"],
        "tags": ["instant", "souvenir", "photo", "moment"],
    },
}

TEMPLATES = {
    "poetique": [
        "Dans {w}, le temps ralentit et le cœur se souvient. ✨",
        "Il y a dans {w} un murmure que seuls les yeux savent écouter.",
        "{W} s'attarde, et nous restons là, simplement heureux.",
    ],
    "marketing": [
        "{W}, version Blink 🔥 Dis-nous en commentaire ce que ça t'inspire !",
        "Capturé, partagé, adoré : {w} comme tu ne l'as jamais vu. Abonne-toi pour la suite 👉",
        "Ton feed avait besoin de {w}. Partage-le avec quelqu'un qui doit le voir !",
    ],
    "humoristique": [
        "Moi devant {w} : « je fais juste une photo » … 47 photos plus tard 😅",
        "{W} : 10/10. Mon talent de photographe : encore en mise à jour.",
        "Quand {w} pose mieux que toi sur tes propres photos 😂",
    ],
}

STYLE_TAGS = {
    "poetique": ["poesie", "instantpoetique"],
    "marketing": ["mustsee", "trending"],
    "humoristique": ["humour", "lol"],
}


def _mood(img):
    small = img.convert("RGB").resize((64, 64))
    stat = ImageStat.Stat(small)
    r, g, b = (c / 255 for c in stat.mean)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.28:
        return "night"
    if s < 0.12:
        return "bright" if v > 0.7 else "neutral"
    hue = h * 360
    if hue < 50 or hue >= 340:
        return "pink" if hue >= 300 or (r > 0.7 and b > 0.5) else "golden"
    if hue < 170:
        return "green" if hue > 70 else "golden"
    if hue < 260:
        return "blue"
    return "pink"


def local_caption(image_bytes, style="poetique"):
    import io

    img = Image.open(io.BytesIO(image_bytes))
    mood = _mood(img)
    rng = random.Random(hashlib.md5(image_bytes[:4096] + style.encode()).hexdigest())
    word = rng.choice(MOODS[mood]["words"])
    caption = rng.choice(TEMPLATES[style]).format(w=word, W=word[0].upper() + word[1:])
    tags = MOODS[mood]["tags"][:] + STYLE_TAGS[style] + ["photooftheday", "blink"]
    rng.shuffle(tags)
    tags = clean_hashtags(["blink"] + tags)[:8]
    return {"caption": caption, "hashtags": tags, "engine": "local", "mood": mood}
