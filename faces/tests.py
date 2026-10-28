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
        self.assertTrue(Notification.objects.filter(destinataire=self.sami, type="tag").exists())

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


class FaceAPITests(BlinkTestCase):
    def setUp(self):
        self.nour = self.make_user("nour")
        self.sami = self.make_user("sami")
        self.other = self.make_user("other")
        self.befriend(self.nour, self.sami)

    def test_face_encoding_generate_and_get(self):
        self.sami.photo_profil = face_image()
        self.sami.save()
        self.client.force_login(self.sami)

        # GET initially 404
        res = self.client.get("/api/faces/encoding/")
        self.assertEqual(res.status_code, 404)

        # POST generate
        res = self.client.post("/api/faces/encoding/generate/")
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["nb_dimensions"], 128)
        self.assertEqual(len(data["vecteur_encoding"]), 128)

        # GET now 200
        res = self.client.get("/api/faces/encoding/")
        self.assertEqual(res.status_code, 200)

        # DELETE 204
        res = self.client.delete("/api/faces/encoding/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(FaceEncoding.objects.filter(user=self.sami).exists())

    def test_post_detect_faces_and_list(self):
        self.sami.photo_profil = face_image()
        self.sami.save()
        encode_user(self.sami)

        post = Post.objects.create(auteur=self.nour, image=group_photo())
        self.client.force_login(self.nour)

        # Detect faces on post
        res = self.client.post(f"/api/posts/{post.pk}/detect-faces/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 2)

        # GET detected faces on post
        res = self.client.get(f"/api/posts/{post.pk}/detected-faces/")
        self.assertEqual(res.status_code, 200)
        faces_data = res.json()
        self.assertEqual(len(faces_data), 2)
        first_face = faces_data[0]
        self.assertIn("bounding_box", first_face)
        self.assertIn("bounding_box_coords", first_face)
        self.assertTrue(len(first_face["tag_suggestions"]) >= 1)

    def test_tag_suggestion_status_workflow(self):
        post = Post.objects.create(auteur=self.nour, image=make_image())
        face = DetectedFace.objects.create(
            post=post, bounding_box={"top": 10, "right": 30, "bottom": 30, "left": 10}, confiance=0.9
        )
        tag = TagSuggestion.objects.create(detected_face=face, user_suggere=self.sami, auto=True)

        # Sami lists pending suggestions
        self.client.force_login(self.sami)
        res = self.client.get("/api/tags/suggestions/")
        self.assertEqual(res.status_code, 200)
        suggs = res.json()
        self.assertEqual(len(suggs), 1)
        self.assertEqual(suggs[0]["id"], tag.pk)

        # Other user cannot modify
        self.client.force_login(self.other)
        res = self.client.patch(f"/api/tags/suggestions/{tag.pk}/status/", {"statut": "accepte"}, content_type="application/json")
        self.assertEqual(res.status_code, 403)

        # Sami accepts
        self.client.force_login(self.sami)
        res = self.client.patch(f"/api/tags/suggestions/{tag.pk}/status/", {"statut": "accepte"}, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        tag.refresh_from_db()
        face.refresh_from_db()
        self.assertEqual(tag.statut, "accepte")
        self.assertEqual(face.user_identifie, self.sami)

        # Delete detected face
        self.client.force_login(self.nour)
        del_res = self.client.delete(f"/api/detected-faces/{face.pk}/")
        self.assertEqual(del_res.status_code, 204)
        self.assertFalse(DetectedFace.objects.filter(pk=face.pk).exists())
