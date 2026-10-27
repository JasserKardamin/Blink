import io
import logging
import threading
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image

from core.models import Notification, notify

from .engine import cv2, get_engine, load_bgr
from .models import DetectedFace, FaceEncoding, TagSuggestion

logger = logging.getLogger("blink.faces")
_engine_lock = threading.Lock()


def _crop_jpeg(bgr, box, margin=0.25):
    h, w = bgr.shape[:2]
    x, y, fw, fh = box
    mx, my = int(fw * margin), int(fh * margin)
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(w, x + fw + mx), min(h, y + fh + my)
    crop = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
    img = Image.fromarray(crop)
    img.thumbnail((256, 256))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return ContentFile(buf.getvalue(), name=f"visage_{uuid.uuid4().hex[:10]}.jpg")


def encode_user(user):
    """Calcule (ou supprime) l'encodage facial d'un utilisateur depuis sa photo de profil."""
    if not user.photo_profil:
        FaceEncoding.objects.filter(user=user).delete()
        return None
    with _engine_lock:
        engine = get_engine()
        if not engine.recognition:
            return None
        bgr = load_bgr(user.photo_profil)
        faces = engine.detect(bgr)
    if not faces:
        FaceEncoding.objects.filter(user=user).delete()
        return None
    biggest = max(faces, key=lambda f: f["box"][2] * f["box"][3])
    encoding, _ = FaceEncoding.objects.get_or_create(user=user, defaults={"vecteur_encoding": []})
    encoding.vecteur_encoding = biggest["encoding"]
    if encoding.photo_reference:
        encoding.photo_reference.delete(save=False)
    encoding.photo_reference.save("ref.jpg", _crop_jpeg(bgr, biggest["box"]), save=False)
    encoding.save()
    return encoding


def encode_user_by_id(user_id):
    from accounts.models import User

    user = User.objects.filter(pk=user_id).first()
    if user:
        encode_user(user)


def detect_faces_for_post(post):
    """Détecte les visages d'une publication et suggère des tags parmi les amis de l'auteur."""
    for face in post.detected_faces.all():
        face.image_source.delete(save=False)
    post.detected_faces.all().delete()

    with _engine_lock:
        engine = get_engine()
        bgr = load_bgr(post.image)
        faces = engine.detect(bgr)
        known = list(
            FaceEncoding.objects.filter(user__in=post.auteur.friends()).select_related("user")
        ) if engine.recognition else []
        h, w = bgr.shape[:2]
        created, recognized = [], 0
        for face in faces:
            x, y, fw, fh = face["box"]
            best_user, best_score = None, 0.0
            if face["encoding"] is not None:
                for ref in known:
                    if not ref.vecteur_encoding:
                        continue
                    score = engine.similarity(face["encoding"], ref.vecteur_encoding)
                    if score > best_score:
                        best_user, best_score = ref.user, score
            matched = best_user if best_score >= settings.FACE_MATCH_THRESHOLD else None
            detected = DetectedFace(
                post=post,
                bounding_box={
                    "x": round(100 * max(0, x) / w, 2), "y": round(100 * max(0, y) / h, 2),
                    "w": round(100 * fw / w, 2), "h": round(100 * fh / h, 2),
                },
                encoding_detecte=face["encoding"] or [],
                user_identifie=matched,
                # Similarité avec l'ami le plus proche, ou score de détection si aucune référence.
                confiance=round(best_score if known else face["score"], 4),
            )
            detected.image_source.save("visage.jpg", _crop_jpeg(bgr, face["box"]), save=False)
            detected.save()
            if matched:
                recognized += 1
                TagSuggestion.objects.create(detected_face=detected, user_suggere=matched, auto=True)
            created.append(detected)

    from posts.models import AIGeneration

    AIGeneration.objects.create(
        post=post, user=post.auteur, type=AIGeneration.Type.VISAGES, moteur=engine.name,
        result={"visages": len(created), "reconnus": recognized},
    )
    if created:
        msg = (
            f"Blink a reconnu {recognized} ami{'s' if recognized > 1 else ''} sur ta photo — confirme les tags !"
            if recognized else f"{len(created)} visage{'s' if len(created) > 1 else ''} détecté{'s' if len(created) > 1 else ''} sur ta photo : tague tes amis !"
        )
        notify(post.auteur, Notification.Type.IA, msg, lien=f"/visages/post/{post.pk}/")
    return created


def detect_faces_by_post_id(post_id):
    from posts.models import Post

    post = Post.objects.select_related("auteur").filter(pk=post_id).first()
    if post:
        detect_faces_for_post(post)


def confirm_tag(detected_face, user, by_author=True):
    """Valide l'identification d'un ami sur un visage (remplace les autres suggestions)."""
    detected_face.tag_suggestions.exclude(user_suggere=user).delete()
    tag, created = TagSuggestion.objects.get_or_create(
        detected_face=detected_face, user_suggere=user, defaults={"auto": False}
    )
    was_accepted = tag.statut == TagSuggestion.Statut.ACCEPTE
    tag.statut = TagSuggestion.Statut.ACCEPTE
    tag.save(update_fields=["statut"])
    detected_face.user_identifie = user
    detected_face.save(update_fields=["user_identifie"])
    if not was_accepted:
        post = detected_face.post
        notify(
            user, Notification.Type.TAG, f"{post.auteur} t'a identifié(e) sur une photo.",
            acteur=post.auteur, lien=post.get_absolute_url(),
        )
    return tag
