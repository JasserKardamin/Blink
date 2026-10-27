"""
Transcription audio → texte (Gestion 2).

Ordre de préférence : Whisper (Hugging Face) puis Gemini (audio multimodal).
Sans clé d'API, la transcription passe en statut « erreur » avec un message
explicite et l'utilisateur peut saisir le texte manuellement.
"""
import logging
import mimetypes

from core.ai_clients import AIUnavailable, gemini_enabled, gemini_json, hf_enabled, hf_whisper

from .models import AudioComment, AudioPost, Transcription

logger = logging.getLogger("blink.audio")

MIME_OVERRIDES = {"webm": "audio/webm", "ogg": "audio/ogg", "oga": "audio/ogg", "m4a": "audio/mp4", "mp4": "audio/mp4"}

GEMINI_PROMPT = (
    "Transcris fidèlement ce message vocal dans sa langue d'origine, sans le traduire ni le résumer. "
    'Réponds en JSON : {"text": "...", "language": "code ISO 639-1 (fr, en, ar...)"}. '
    'Si aucun mot n\'est audible, renvoie {"text": "", "language": ""}.'
)


def guess_mime(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return MIME_OVERRIDES.get(ext) or mimetypes.guess_type(name)[0] or "audio/webm"


def detect_language(text):
    """Détection de langue minimaliste (utilisée quand Whisper ne la fournit pas)."""
    if not text:
        return ""
    if any("؀" <= ch <= "ۿ" for ch in text):
        return "ar"
    lowered = f" {text.lower()} "
    fr = sum(lowered.count(w) for w in (" le ", " la ", " les ", " est ", " et ", " je ", " on ", " de ", " un ", " une "))
    en = sum(lowered.count(w) for w in (" the ", " is ", " and ", " i ", " you ", " of ", " to ", " a "))
    return "fr" if fr >= en else "en"


def run_transcription(audio_bytes, filename):
    """Retourne (texte, langue, moteur) ou lève AIUnavailable."""
    mime = guess_mime(filename)
    errors = []
    if hf_enabled():
        try:
            text = hf_whisper(audio_bytes, mime)
            return text, detect_language(text), "whisper"
        except AIUnavailable as exc:
            errors.append(str(exc))
    if gemini_enabled():
        try:
            data = gemini_json(GEMINI_PROMPT, audio_bytes=audio_bytes, audio_mime=mime, temperature=0.1)
            text = str(data.get("text", "")).strip()
            return text, (data.get("language") or detect_language(text))[:10], "gemini"
        except AIUnavailable as exc:
            errors.append(str(exc))
    if not errors:
        errors.append("Aucun service de transcription configuré (HF_TOKEN ou GEMINI_API_KEY).")
    raise AIUnavailable(" | ".join(errors))


def transcribe_object(obj):
    """Transcrit un AudioPost ou un AudioComment et met à jour sa Transcription."""
    if isinstance(obj, AudioPost):
        transcription, _ = Transcription.objects.get_or_create(audio_post=obj)
    else:
        transcription = obj.transcription or Transcription.objects.create()
        if obj.transcription_id != transcription.pk:
            obj.transcription = transcription
            obj.save(update_fields=["transcription"])

    transcription.statut = Transcription.Statut.EN_ATTENTE
    transcription.erreur = ""
    transcription.save(update_fields=["statut", "erreur"])

    try:
        obj.fichier_audio.open("rb")
        audio_bytes = obj.fichier_audio.read()
        obj.fichier_audio.close()
        text, lang, engine = run_transcription(audio_bytes, obj.fichier_audio.name)
        transcription.texte = text or "(aucune parole détectée)"
        transcription.langue = lang
        transcription.moteur = engine
        transcription.statut = Transcription.Statut.TERMINE
    except AIUnavailable as exc:
        transcription.statut = Transcription.Statut.ERREUR
        transcription.erreur = str(exc)[:255]
    except OSError as exc:
        logger.exception("Lecture audio impossible")
        transcription.statut = Transcription.Statut.ERREUR
        transcription.erreur = f"Fichier audio illisible : {exc}"[:255]
    transcription.save()

    from posts.models import AIGeneration

    AIGeneration.objects.create(
        post=obj.post if obj.post_id else None,
        user=obj.user,
        type=AIGeneration.Type.TRANSCRIPTION,
        moteur=transcription.moteur or "aucun",
        result={"statut": transcription.statut, "langue": transcription.langue, "erreur": transcription.erreur},
    )
    return transcription


def transcribe_by_id(model_name, pk):
    """Point d'entrée des tâches d'arrière-plan."""
    model = AudioPost if model_name == "post" else AudioComment
    obj = model.objects.filter(pk=pk).select_related("post", "user").first()
    if obj:
        transcribe_object(obj)
