"""
Génération d'images IA (Gestion 3 – Hugging Face / Stable Diffusion).

- Filtre IA : stylisation fidèle de la photo (OpenCV), instantanée.
- Image dérivée / avatar : Gemini décrit la photo, Stable Diffusion la
  réinterprète dans le style choisi. Sans clé, repli sur le filtre local.
"""
import io
import logging
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image

from core.ai_clients import AIUnavailable, gemini_json, hf_text_to_image, image_to_jpeg_bytes

from .filters import apply_filter
from .models import GeneratedImage

logger = logging.getLogger("blink.aistudio")

STYLE_PROMPTS = {
    "anime": "anime illustration, studio ghibli inspired, cel shading, vibrant colors, clean line art",
    "peinture": "oil painting on canvas, thick impasto brush strokes, impressionist, rich colors",
    "cyberpunk": "cyberpunk style, neon lights, magenta and cyan, futuristic, rainy night, cinematic",
    "aquarelle": "delicate watercolor painting, soft washes, paper texture, pastel tones",
    "croquis": "detailed pencil sketch, graphite, cross hatching, black and white drawing",
    "vintage": "vintage 1970s film photograph, kodak portra, warm sepia tones, film grain",
}

DESCRIBE_PROMPT = (
    "Describe this photo in one concise English sentence (max 40 words) usable as a prompt for an image "
    "generation model: main subjects, setting, composition, lighting. Do not name real people. "
    'Answer in JSON: {"description": "..."}'
)


def describe_image(image_file, fallback=""):
    try:
        data = gemini_json(DESCRIBE_PROMPT, image_bytes=image_to_jpeg_bytes(image_file, 768), temperature=0.4)
        return str(data.get("description", "")).strip() or fallback
    except AIUnavailable:
        return fallback


def build_prompt(gen, description):
    style_desc = STYLE_PROMPTS.get(gen.style, STYLE_PROMPTS["anime"])
    caption = gen.post.caption if gen.post_id else ""
    if gen.template_id:
        return gen.template.render(description=description, style=style_desc, caption=caption)
    if gen.type == GeneratedImage.Type.AVATAR:
        return f"stylized profile avatar portrait, head and shoulders, centered, {description}, {style_desc}, high quality"
    return f"{description}, {style_desc}, highly detailed, masterpiece"


def _save_result(gen, img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    gen.image_generee.save(f"{gen.type}_{gen.style}_{uuid.uuid4().hex[:8]}.jpg", ContentFile(buf.getvalue()), save=False)


def process_generation(gen):
    """Calcule l'image d'une GeneratedImage et met à jour son statut."""
    gen.image_originale.open("rb")
    original = Image.open(gen.image_originale)
    original.load()
    gen.image_originale.close()

    params = gen.filtre.parametres if gen.filtre_id else {}
    try:
        if gen.type == GeneratedImage.Type.FILTRE:
            result = apply_filter(original, gen.style, params)
            gen.modele = "opencv-stylisation"
            gen.prompt = gen.prompt or f"Filtre local « {gen.get_style_display()} »"
        else:
            fallback = (gen.post.caption if gen.post_id and gen.post.caption else "a beautiful scene")
            if gen.type == GeneratedImage.Type.AVATAR:
                fallback = "a friendly person smiling"
            description = describe_image(gen.image_originale, fallback=fallback)
            gen.prompt = build_prompt(gen, description)
            try:
                result = hf_text_to_image(gen.prompt)
                gen.modele = settings.HF_IMAGE_MODEL
            except AIUnavailable as exc:
                logger.info("Diffusion indisponible (%s) : repli sur le filtre local", exc)
                result = apply_filter(original, gen.style, params)
                gen.modele = "opencv-stylisation (repli local)"
        _save_result(gen, result)
        gen.statut = GeneratedImage.Statut.TERMINE
        gen.erreur = ""
    except Exception as exc:  # noqa: BLE001 - on veut toujours un statut final
        logger.exception("Génération d'image échouée")
        gen.statut = GeneratedImage.Statut.ERREUR
        gen.erreur = str(exc)[:255]
    gen.save()

    from posts.models import AIGeneration

    AIGeneration.objects.create(
        post=gen.post, user=gen.user, type=AIGeneration.Type.IMAGE, moteur=gen.modele[:60],
        prompt=gen.prompt, result={"generated_image": gen.pk, "statut": gen.statut, "style": gen.style},
    )
    return gen


def process_generation_by_id(pk):
    gen = GeneratedImage.objects.select_related("post", "filtre", "template", "user").filter(pk=pk).first()
    if gen:
        process_generation(gen)


def copy_source_image(field_file):
    """Duplique une image source (post ou photo de profil) pour l'historique de génération."""
    field_file.open("rb")
    data = field_file.read()
    field_file.close()
    name = field_file.name.rsplit("/", 1)[-1]
    return ContentFile(data, name=name)
