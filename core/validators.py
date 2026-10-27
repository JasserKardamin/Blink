from django.conf import settings
from django.core.exceptions import ValidationError

AUDIO_EXTENSIONS = {"webm", "ogg", "oga", "mp3", "wav", "m4a", "aac", "flac", "mp4"}


def validate_image_size(file):
    limit = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if file and getattr(file, "size", 0) > limit:
        raise ValidationError(f"L'image ne doit pas dépasser {settings.MAX_IMAGE_SIZE_MB} Mo.")


def validate_audio_file(file):
    limit = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
    if not file:
        return
    if getattr(file, "size", 0) > limit:
        raise ValidationError(f"Le fichier audio ne doit pas dépasser {settings.MAX_AUDIO_SIZE_MB} Mo.")
    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if ext not in AUDIO_EXTENSIONS:
        raise ValidationError("Format audio non supporté (webm, ogg, mp3, wav, m4a, flac).")
