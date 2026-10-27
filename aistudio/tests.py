from unittest import mock

from django.urls import reverse
from PIL import Image

from aistudio.filters import FILTERS, apply_filter
from aistudio.models import AIPromptTemplate, GeneratedImage, ImageFilter
from core.testing import BlinkTestCase, make_image
from posts.models import Post


class FilterTests(BlinkTestCase):
    def test_all_local_filters(self):
        img = Image.new("RGB", (120, 90), (200, 120, 80))
        for name in FILTERS:
            out = apply_filter(img, name, {"intensite": 0.8, "saturation": 1.2, "contraste": 1.1})
            self.assertEqual(out.size, (120, 90), name)
            self.assertEqual(out.mode, "RGB")

    def test_system_filters_seeded(self):
        self.assertEqual(ImageFilter.objects.filter(user__isnull=True).count(), 6)


class StudioViewTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami = self.make_user("nour"), self.make_user("sami")
        self.post = Post.objects.create(auteur=self.nour, image=make_image(size=(200, 160)), caption="Plage")
        self.client.force_login(self.nour)

    def generate(self, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("aistudio:generate", args=[self.post.pk]), data)

    def test_filter_generation(self):
        resp = self.generate(type="filtre", style="cyberpunk")
        gen = GeneratedImage.objects.get()
        self.assertRedirects(resp, gen.get_absolute_url())
        self.assertEqual(gen.statut, "termine")
        self.assertTrue(gen.image_generee)
        self.assertEqual(gen.modele, "opencv-stylisation")

    def test_derived_image_falls_back_locally(self):
        self.generate(type="derivee", style="aquarelle")
        gen = GeneratedImage.objects.get()
        self.assertEqual(gen.statut, "termine")
        self.assertIn("repli local", gen.modele)
        self.assertIn("watercolor", gen.prompt)

    def test_derived_image_with_diffusion(self):
        with self.settings(HF_TOKEN="t"), mock.patch(
            "aistudio.services.hf_text_to_image", return_value=Image.new("RGB", (64, 64), "purple")
        ) as sd:
            self.generate(type="derivee", style="anime")
        sd.assert_called_once()
        self.assertEqual(GeneratedImage.objects.get().modele, "stabilityai/stable-diffusion-xl-base-1.0")

    def test_custom_filter_and_template(self):
        filt = ImageFilter.objects.create(nom="Mon néon", user=self.nour, parametres={"base": "cyberpunk", "saturation": 1.5})
        tpl = AIPromptTemplate.objects.create(user=self.nour, nom="Ciné", template_prompt="{description}, {style}, cinematic")
        self.generate(type="derivee", style="anime", filtre=filt.pk, template=tpl.pk)
        gen = GeneratedImage.objects.get()
        self.assertEqual(gen.style, "cyberpunk")  # imposé par le filtre
        self.assertTrue(gen.prompt.endswith("cinematic"))

    def test_cannot_generate_from_others_post(self):
        self.client.force_login(self.sami)
        self.assertEqual(self.client.post(reverse("aistudio:generate", args=[self.post.pk]), {}).status_code, 404)

    def test_publish_and_use_as_avatar(self):
        self.generate(type="filtre", style="vintage")
        gen = GeneratedImage.objects.get()
        self.client.post(reverse("aistudio:use_avatar", args=[gen.pk]))
        self.nour.profile.refresh_from_db()
        self.assertTrue(self.nour.profile.avatar)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("aistudio:publish", args=[gen.pk]))
        self.assertEqual(Post.objects.filter(auteur=self.nour).count(), 2)

    def test_avatar_requires_profile_photo(self):
        self.assertRedirects(self.client.get(reverse("aistudio:avatar")), reverse("accounts:edit"))
        self.nour.photo_profil = make_image("moi.jpg")
        self.nour.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("aistudio:avatar"), {"style": "anime"})
        self.assertEqual(GeneratedImage.objects.get().type, "avatar")

    def test_template_and_filter_crud_ownership(self):
        self.client.post(reverse("aistudio:template_create"), {"nom": "T", "type": "image", "template_prompt": "{description}"})
        self.client.post(reverse("aistudio:filter_create"), {"nom": "F", "base": "anime", "intensite": 0.5, "saturation": 1, "contraste": 1})
        tpl, filt = AIPromptTemplate.objects.get(), ImageFilter.objects.get(user=self.nour)
        self.assertEqual(filt.parametres["intensite"], 0.5)
        self.client.force_login(self.sami)
        self.assertEqual(self.client.post(reverse("aistudio:template_delete", args=[tpl.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("aistudio:filter_delete", args=[filt.pk])).status_code, 403)
