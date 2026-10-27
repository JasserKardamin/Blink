"""Outils communs aux tests (images de test, médias temporaires, IA hors-ligne)."""
import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts.models import Friendship, User

TEST_DATA = Path(__file__).resolve().parent / "tests_data"


def make_image(name="photo.jpg", color=(255, 140, 90), size=(320, 240)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def face_image(name="face.jpg"):
    return SimpleUploadedFile(name, (TEST_DATA / "face.jpg").read_bytes(), content_type="image/jpeg")


def fake_audio(name="vocal.webm"):
    return SimpleUploadedFile(name, b"\x1aE\xdf\xa3" + b"\x00" * 2048, content_type="audio/webm")


class BlinkTestCase(TestCase):
    """Médias dans un dossier temporaire, tâches synchrones, aucun appel réseau IA."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix="blink-test-")
        cls._override = override_settings(
            MEDIA_ROOT=cls._media, BLINK_SYNC_TASKS=True, GEMINI_API_KEY="", HF_TOKEN="",
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def make_user(self, username, **extra):
        return User.objects.create_user(username, f"{username}@test.tn", "motdepasse123", **extra)

    def befriend(self, a, b):
        Friendship.objects.create(user_from=a, user_to=b, statut=Friendship.Statut.ACCEPTE)
