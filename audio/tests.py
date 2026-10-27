from unittest import mock

from django.urls import reverse

from audio.models import AudioComment, AudioPost, Transcription
from audio.services import detect_language, guess_mime, run_transcription
from core.ai_clients import AIUnavailable
from core.models import Notification
from core.testing import BlinkTestCase, fake_audio, make_image
from posts.models import Post


class TranscriptionServiceTests(BlinkTestCase):
    def test_no_service_configured(self):
        with self.assertRaises(AIUnavailable):
            run_transcription(b"data", "a.webm")

    def test_whisper_then_gemini_fallback(self):
        with self.settings(HF_TOKEN="t", GEMINI_API_KEY="k"), \
                mock.patch("audio.services.hf_whisper", side_effect=AIUnavailable("quota")), \
                mock.patch("audio.services.gemini_json", return_value={"text": "Bonjour à tous", "language": "fr"}):
            self.assertEqual(run_transcription(b"x", "a.ogg"), ("Bonjour à tous", "fr", "gemini"))

    def test_helpers(self):
        self.assertEqual(guess_mime("a.webm"), "audio/webm")
        self.assertEqual(guess_mime("a.m4a"), "audio/mp4")
        self.assertEqual(detect_language("Je prends les sandwichs et on y va"), "fr")
        self.assertEqual(detect_language("I think the weather is nice"), "en")
        self.assertEqual(detect_language("مرحبا بكم"), "ar")


class AudioViewsTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami = self.make_user("nour"), self.make_user("sami")
        self.befriend(self.nour, self.sami)
        self.post = Post.objects.create(auteur=self.nour, image=make_image())

    def test_audio_post_transcribed(self):
        self.client.force_login(self.nour)
        with self.settings(HF_TOKEN="t"), mock.patch("audio.services.hf_whisper", return_value="Trop beau ce coucher de soleil"), \
                self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse("audio:create"), {"fichier_audio": fake_audio(), "description": "Test", "duree": 8})
        audio = AudioPost.objects.get()
        self.assertRedirects(resp, audio.get_absolute_url())
        t = audio.transcription
        self.assertEqual((t.statut, t.texte, t.langue, t.moteur), ("termine", "Trop beau ce coucher de soleil", "fr", "whisper"))

    def test_rejects_non_audio(self):
        self.client.force_login(self.nour)
        resp = self.client.post(reverse("audio:create"), {"fichier_audio": make_image("x.jpg"), "duree": 3})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AudioPost.objects.exists())

    def test_voice_comment(self):
        self.client.force_login(self.sami)
        with self.settings(GEMINI_API_KEY="k"), \
                mock.patch("audio.services.gemini_json", return_value={"text": "Je prends les sandwichs.", "language": "fr"}), \
                self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse("audio:comment_create", args=[self.post.pk]),
                                    {"fichier_audio": fake_audio(), "duree": 3}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 201)
        comment = AudioComment.objects.get()
        self.assertEqual(comment.transcription.texte, "Je prends les sandwichs.")
        self.assertEqual(comment.transcription.owner, self.sami)
        self.assertTrue(Notification.objects.filter(destinataire=self.nour, type="commentaire_vocal").exists())
        # Le post affiche le commentaire vocal et sa transcription.
        page = self.client.get(self.post.get_absolute_url())
        self.assertContains(page, "Je prends les sandwichs.")

    def test_manual_transcription_edit_owner_only(self):
        audio = AudioPost.objects.create(user=self.nour, fichier_audio=fake_audio(), duree=2)
        t = Transcription.objects.create(audio_post=audio, statut="erreur", erreur="aucun service")
        url = reverse("audio:transcription_update", args=[t.pk])
        self.client.force_login(self.sami)
        self.assertEqual(self.client.post(url, {"texte": "hack", "langue": "fr"}).status_code, 403)
        self.client.force_login(self.nour)
        self.client.post(url, {"texte": "Bonjour", "langue": "fr"})
        t.refresh_from_db()
        self.assertEqual((t.texte, t.statut, t.moteur), ("Bonjour", "termine", "manuel"))

    def test_retranscribe(self):
        audio = AudioPost.objects.create(user=self.nour, fichier_audio=fake_audio(), duree=2)
        Transcription.objects.create(audio_post=audio, statut="erreur")
        self.client.force_login(self.nour)
        with self.settings(HF_TOKEN="t"), mock.patch("audio.services.hf_whisper", return_value="Salut"), \
                self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("audio:retranscribe", args=["post", audio.pk]))
        audio.transcription.refresh_from_db()
        self.assertEqual(audio.transcription.texte, "Salut")

    def test_audio_on_private_post_hidden(self):
        private = Post.objects.create(auteur=self.nour, image=make_image(), visibilite="prive")
        audio = AudioPost.objects.create(user=self.nour, post=private, fichier_audio=fake_audio())
        self.client.force_login(self.sami)
        self.assertEqual(self.client.get(audio.get_absolute_url()).status_code, 404)
