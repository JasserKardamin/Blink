from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Notification
from core.testing import BlinkTestCase, make_image
from posts.models import Comment, Post


class APITests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami = self.make_user("nour"), self.make_user("sami")
        self.befriend(self.nour, self.sami)
        self.api = APIClient()

    def test_token_auth_and_me(self):
        resp = self.api.post("/api/auth/token/", {"username": "nour", "password": "motdepasse123"})
        token = resp.json()["token"]
        self.assertEqual(token, Token.objects.get(user=self.nour).key)
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.api.get("/api/users/me/").json()["username"], "nour")

    def test_anonymous_sees_public_only(self):
        Post.objects.create(auteur=self.nour, image=make_image(), visibilite="public")
        Post.objects.create(auteur=self.nour, image=make_image(), visibilite="amis")
        self.assertEqual(self.api.get("/api/posts/").json()["count"], 1)
        self.assertEqual(self.api.post("/api/posts/", {}).status_code, 403)

    def test_create_react_comment(self):
        self.api.force_authenticate(self.nour)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.api.post("/api/posts/", {"image": make_image(), "caption": "Hello #api", "visibilite": "amis"}, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.content)
        post_id = resp.json()["id"]
        self.assertEqual(resp.json()["hashtags"], ["api"])

        self.api.force_authenticate(self.sami)
        self.assertEqual(self.api.get("/api/posts/?feed=1").json()["count"], 1)
        self.assertEqual(self.api.post(f"/api/posts/{post_id}/react/", {"type": "love"}).json()["count"], 1)
        self.assertEqual(self.api.post(f"/api/posts/{post_id}/comments/", {"contenu": "Top"}).status_code, 201)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(destinataire=self.nour).count(), 2)
        # Un autre utilisateur ne peut pas modifier la publication.
        self.assertEqual(self.api.patch(f"/api/posts/{post_id}/", {"caption": "x"}).status_code, 403)

    def test_ai_caption_endpoint(self):
        post = Post.objects.create(auteur=self.nour, image=make_image())
        self.api.force_authenticate(self.nour)
        resp = self.api.post("/api/ai/caption/", {"post_id": post.pk, "style": "marketing"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("blink", resp.json()["hashtags"])
        self.api.force_authenticate(self.sami)
        self.assertEqual(self.api.post("/api/ai/caption/", {"post_id": post.pk}).status_code, 404)
        self.assertEqual(self.api.post("/api/ai/caption/", {}).status_code, 400)

    def test_notifications_unread(self):
        Notification.objects.create(destinataire=self.nour, type="ia", message="Test")
        self.api.force_authenticate(self.nour)
        self.assertEqual(self.api.get("/api/notifications/unread_count/").json()["count"], 1)
        self.api.post("/api/notifications/mark_all_read/")
        self.assertEqual(self.api.get("/api/notifications/unread_count/").json()["count"], 0)

    def test_ai_status(self):
        data = self.api.get("/api/ai/status/").json()
        self.assertEqual(data["gemini"], False)
        self.assertIn("face_recognition", data)
