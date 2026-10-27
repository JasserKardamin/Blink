import io
from unittest import mock

from django.urls import reverse
from PIL import Image

from audio.models import AudioPost, Transcription
from core.models import Notification, Report
from core.testing import BlinkTestCase, fake_audio, make_image
from posts import ai
from posts.models import AIGeneration, Comment, Post, Reaction


class VisibilityTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami, self.lina = self.make_user("nour"), self.make_user("sami"), self.make_user("lina")
        self.befriend(self.nour, self.sami)
        self.public = Post.objects.create(auteur=self.nour, image=make_image(), visibilite="public")
        self.friends = Post.objects.create(auteur=self.nour, image=make_image(), visibilite="amis")
        self.private = Post.objects.create(auteur=self.nour, image=make_image(), visibilite="prive")

    def visible(self, user):
        return set(Post.objects.visible_to(user).values_list("pk", flat=True))

    def test_visibility_rules(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(self.visible(AnonymousUser()), {self.public.pk})
        self.assertEqual(self.visible(self.lina), {self.public.pk})
        self.assertEqual(self.visible(self.sami), {self.public.pk, self.friends.pk})
        self.assertEqual(self.visible(self.nour), {self.public.pk, self.friends.pk, self.private.pk})

    def test_detail_view_respects_visibility(self):
        self.client.force_login(self.lina)
        self.assertEqual(self.client.get(self.friends.get_absolute_url()).status_code, 404)
        self.client.force_login(self.sami)
        self.assertEqual(self.client.get(self.friends.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(self.private.get_absolute_url()).status_code, 404)

    def test_masked_posts_hidden(self):
        self.public.est_masque = True
        self.public.save()
        self.assertNotIn(self.public.pk, self.visible(self.nour))

    def test_feed_contains_friends_and_followed(self):
        self.sami.follow(self.lina)
        lina_post = Post.objects.create(auteur=self.lina, image=make_image(), visibilite="public")
        feed = set(Post.objects.feed_for(self.sami).values_list("pk", flat=True))
        self.assertEqual(feed, {self.public.pk, self.friends.pk, lina_post.pk})


class PostFlowTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami = self.make_user("nour"), self.make_user("sami")
        self.befriend(self.nour, self.sami)

    def test_create_post_with_audio(self):
        self.client.force_login(self.nour)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse("posts:create"), {
                "image": make_image(), "caption": "Coucher de soleil #goldenhour", "visibilite": "amis",
                "caption_ia": "Le soleil s'endort", "hashtags_ia": "#sunset #blink", "caption_style": "poetique",
                "audio": fake_audio(), "audio_duree": "12",
            })
        post = Post.objects.get()
        self.assertRedirects(resp, post.get_absolute_url())
        self.assertEqual(post.auteur, self.nour)
        self.assertEqual(post.get_hashtags(), ["goldenhour", "sunset", "blink"])
        audio = AudioPost.objects.get(post=post)
        self.assertEqual(audio.duree, 12)
        # Pas de clé d'API en test : la transcription échoue proprement.
        self.assertEqual(audio.transcription.statut, Transcription.Statut.ERREUR)
        self.assertTrue(AIGeneration.objects.filter(post=post, type="visages").exists())

    def test_reaction_toggle_json(self):
        post = Post.objects.create(auteur=self.nour, image=make_image())
        self.client.force_login(self.sami)
        url = reverse("posts:react", args=[post.pk])
        data = self.client.post(url, {"type": "love"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertEqual(data, {"active": True, "type": "love", "count": 1, "counts": {"love": 1}})
        data = self.client.post(url, {"type": "haha"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertEqual((data["type"], data["count"]), ("haha", 1))
        data = self.client.post(url, {"type": "haha"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertEqual((data["active"], data["count"]), (False, 0))
        self.assertTrue(Notification.objects.filter(destinataire=self.nour, type="reaction").exists())

    def test_comment_update_delete_permissions(self):
        post = Post.objects.create(auteur=self.nour, image=make_image())
        self.client.force_login(self.sami)
        self.client.post(reverse("posts:comment", args=[post.pk]), {"contenu": "Magnifique !"})
        comment = Comment.objects.get()
        self.assertEqual(self.client.post(reverse("posts:comment_update", args=[comment.pk]), {"contenu": "Super"}).status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.contenu, "Super")
        # L'auteur du post peut supprimer, un tiers non.
        lina = self.make_user("lina")
        self.client.force_login(lina)
        self.assertEqual(self.client.post(reverse("posts:comment_delete", args=[comment.pk])).status_code, 404)
        self.client.force_login(self.nour)
        self.client.post(reverse("posts:comment_delete", args=[comment.pk]))
        self.assertFalse(Comment.objects.exists())

    def test_only_author_can_edit_or_delete(self):
        post = Post.objects.create(auteur=self.nour, image=make_image())
        self.client.force_login(self.sami)
        self.assertEqual(self.client.get(reverse("posts:update", args=[post.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("posts:delete", args=[post.pk])).status_code, 403)
        self.client.force_login(self.nour)
        self.client.post(reverse("posts:update", args=[post.pk]), {"caption": "Nouvelle", "hashtags_ia": "", "visibilite": "prive"})
        post.refresh_from_db()
        self.assertEqual((post.caption, post.visibilite), ("Nouvelle", "prive"))
        self.client.post(reverse("posts:delete", args=[post.pk]))
        self.assertFalse(Post.objects.exists())

    def test_report_once(self):
        post = Post.objects.create(auteur=self.nour, image=make_image())
        self.client.force_login(self.sami)
        for _ in range(2):
            self.client.post(reverse("posts:report", args=[post.pk]), {"motif": "spam", "details": ""})
        self.assertEqual(Report.objects.count(), 1)

    def test_hashtag_page(self):
        tagged = Post.objects.create(auteur=self.nour, image=make_image(), caption="Plage #ete")
        Post.objects.create(auteur=self.nour, image=make_image(), caption="Plage #eteindre")
        resp = self.client.get(reverse("posts:hashtag", args=["ete"]))
        self.assertEqual([p.pk for p in resp.context["posts"]], [tagged.pk])


class CaptionAITests(BlinkTestCase):
    def image_bytes(self, color):
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
        return buf.getvalue()

    def test_local_caption_styles(self):
        for style in ("poetique", "marketing", "humoristique"):
            result = ai.local_caption(self.image_bytes((255, 150, 60)), style)
            self.assertTrue(result["caption"])
            self.assertIn("blink", result["hashtags"])
            self.assertEqual(result["mood"], "golden")
        self.assertEqual(ai.local_caption(self.image_bytes((10, 10, 20)))["mood"], "night")

    def test_gemini_result_is_cleaned(self):
        fake = {"caption": "Le soleil s'endort, nous, on reste.", "hashtags": ["#GoldenHour", "entre amis", "Été"]}
        with self.settings(GEMINI_API_KEY="x"), mock.patch("posts.ai.gemini_json", return_value=fake):
            result = ai.generate_caption(make_image(), "poetique")
        self.assertEqual(result["engine"], "gemini")
        self.assertEqual(result["hashtags"], ["goldenhour", "entreamis", "ete", "blink"])

    def test_caption_api_falls_back_to_local(self):
        user = self.make_user("nour")
        self.client.force_login(user)
        resp = self.client.post(reverse("ai_caption"), {"image": make_image(), "style": "humoristique"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["engine"], "local")
        self.assertEqual(AIGeneration.objects.get().type, "legende")

    def test_generate_ai_on_post(self):
        user = self.make_user("nour")
        post = Post.objects.create(auteur=user, image=make_image())
        post.generate_ai("marketing")
        post.refresh_from_db()
        self.assertTrue(post.caption_ia)
        self.assertTrue(post.hashtags_ia.startswith("#"))
        self.assertEqual(post.caption_style, "marketing")

    def test_reaction_model_toggle(self):
        user = self.make_user("nour")
        post = Post.objects.create(auteur=user, image=make_image())
        self.assertIsNotNone(Reaction.toggle(user, post, "like"))
        self.assertIsNone(Reaction.toggle(user, post, "like"))
