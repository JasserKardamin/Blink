import io
import unittest

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image, ImageOps

from core.models import Notification
from core.testing import TEST_DATA, BlinkTestCase, face_image, make_image
from faces.engine import model_path
from faces.models import DetectedFace, FaceEncoding, TagSuggestion
from faces.services import detect_faces_for_post, encode_user
from posts.models import Post

MODELS_READY = model_path("sface")[0].exists() and model_path("yunet")[0].exists()


def group_photo():
    """Deux fois le même visage (dont une version miroir) sur une même photo."""
    face = Image.open(TEST_DATA / "face.jpg").convert("RGB")
    canvas = Image.new("RGB", (face.width * 2, face.height))
    canvas.paste(face, (0, 0))
    canvas.paste(ImageOps.mirror(face), (face.width, 0))
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG")
    return SimpleUploadedFile("groupe.jpg", buf.getvalue(), content_type="image/jpeg")


@unittest.skipUnless(MODELS_READY, "Modèles ONNX absents (python manage.py setup_face_models)")
class FaceRecognitionTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami, self.lina = self.make_user("nour"), self.make_user("sami"), self.make_user("lina")
        self.befriend(self.nour, self.sami)

    def test_encode_user(self):
        self.sami.photo_profil = face_image()
        self.sami.save()
        enc = encode_user(self.sami)
        self.assertEqual(len(enc.vecteur_encoding), 128)
        self.assertTrue(enc.photo_reference)

    def test_no_face_removes_encoding(self):
        self.sami.photo_profil = make_image()
        self.sami.save()
        self.assertIsNone(encode_user(self.sami))
        self.assertFalse(FaceEncoding.objects.exists())

    def test_friends_recognized_on_group_photo(self):
        self.sami.photo_profil = face_image()
        self.sami.save()
        encode_user(self.sami)
        post = Post.objects.create(auteur=self.nour, image=group_photo())
        faces = detect_faces_for_post(post)
        self.assertEqual(len(faces), 2)
        self.assertTrue(all(f.user_identifie == self.sami for f in faces))
        self.assertTrue(all(f.confiance > 0.363 for f in faces))
        self.assertEqual(TagSuggestion.objects.filter(statut="en_attente").count(), 2)
        self.assertTrue(Notification.objects.filter(destinataire=self.nour, type="ia").exists())

    def test_non_friends_not_suggested(self):
        self.lina.photo_profil = face_image()
        self.lina.save()
        encode_user(self.lina)
        post = Post.objects.create(auteur=self.nour, image=group_photo())
        faces = detect_faces_for_post(post)
        self.assertEqual(len(faces), 2)
        self.assertFalse(TagSuggestion.objects.exists())


class TaggingViewTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami = self.make_user("nour"), self.make_user("sami")
        self.befriend(self.nour, self.sami)
        self.post = Post.objects.create(auteur=self.nour, image=make_image())
        self.face = DetectedFace.objects.create(post=self.post, bounding_box={"x": 10, "y": 10, "w": 20, "h": 20}, confiance=0.8)
        TagSuggestion.objects.create(detected_face=self.face, user_suggere=self.sami)

    def test_confirm_and_manual_tags(self):
        self.client.force_login(self.nour)
        self.assertEqual(self.client.get(reverse("faces:post_tags", args=[self.post.pk])).status_code, 200)
        self.client.post(reverse("faces:post_tags", args=[self.post.pk]), {f"face_{self.face.pk}": self.sami.pk})
        tag = TagSuggestion.objects.get(detected_face=self.face)
        self.assertEqual(tag.statut, "accepte")
        self.assertEqual(self.post.tagged_users(), [self.sami])
        self.assertTrue(Notification.objects.filter(destinataire=self.sami, type="tag").exists())

    def test_only_author_manages_tags(self):
        self.client.force_login(self.sami)
        self.assertEqual(self.client.get(reverse("faces:post_tags", args=[self.post.pk])).status_code, 404)

    def test_tagged_user_can_remove_tag(self):
        tag = TagSuggestion.objects.get()
        tag.statut = "accepte"
        tag.save()
        self.client.force_login(self.sami)
        self.client.post(reverse("faces:remove_tag", args=[tag.pk]))
        tag.refresh_from_db()
        self.assertEqual(tag.statut, "refuse")
        self.assertEqual(self.post.tagged_users(), [])

    def test_delete_encoding(self):
        FaceEncoding.objects.create(user=self.sami, vecteur_encoding=[0.1] * 128, photo_reference=make_image())
        self.client.force_login(self.sami)
        self.client.post(reverse("faces:encoding", args=["supprimer"]))
        self.assertFalse(FaceEncoding.objects.exists())
