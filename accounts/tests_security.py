import re
from datetime import date

import pyotp
from django.core import mail
from django.urls import reverse

from accounts import two_factor
from accounts.models import TwoFactorDevice, User
from core.models import Report
from core.testing import BlinkTestCase, make_image
from posts.models import Post

PASSWORD = "motdepasse123"


class PasswordResetTests(BlinkTestCase):
    def test_reset_by_email_end_to_end(self):
        user = self.make_user("sami")
        resp = self.client.post(reverse("accounts:password_reset"), {"email": "SAMI@test.tn"})
        self.assertRedirects(resp, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["sami@test.tn"])
        link = re.search(r"https?://[^\s]+/mot-de-passe/reinitialiser/[^\s]+/", message.body).group(0)

        resp = self.client.get(link, follow=True)  # Django redirige vers une URL « set-password »
        self.assertTrue(resp.context["validlink"])
        resp = self.client.post(resp.redirect_chain[-1][0], {
            "new_password1": "NouveauSecret!2026", "new_password2": "NouveauSecret!2026",
        })
        self.assertRedirects(resp, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("NouveauSecret!2026"))
        # Le lien ne sert qu'une fois.
        self.assertFalse(self.client.get(link, follow=True).context["validlink"])

    def test_unknown_email_sends_nothing_but_same_page(self):
        resp = self.client.post(reverse("accounts:password_reset"), {"email": "personne@test.tn"})
        self.assertRedirects(resp, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_email_rejected(self):
        resp = self.client.post(reverse("accounts:password_reset"), {"email": "pas-un-email"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].errors["email"])


class PasswordChangeTests(BlinkTestCase):
    def setUp(self):
        self.user = self.make_user("lina")
        self.client.force_login(self.user)

    def test_change_password_keeps_session(self):
        resp = self.client.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD, "new_password1": "Toujours!Plus2026", "new_password2": "Toujours!Plus2026",
        })
        self.assertRedirects(resp, reverse("accounts:security"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Toujours!Plus2026"))
        self.assertEqual(self.client.get(reverse("accounts:security")).status_code, 200)

    def test_wrong_old_password_and_weak_new_password(self):
        resp = self.client.post(reverse("accounts:password_change"), {
            "old_password": "faux", "new_password1": "12345678", "new_password2": "12345678",
        })
        self.assertEqual(resp.status_code, 200)
        errors = resp.context["form"].errors
        self.assertIn("old_password", errors)
        self.assertIn("new_password2", errors)  # mot de passe trop courant / numérique

    def test_same_password_rejected(self):
        self.user.set_password("Toujours!Plus2026")
        self.user.save()
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:password_change"), {
            "old_password": "Toujours!Plus2026", "new_password1": "Toujours!Plus2026", "new_password2": "Toujours!Plus2026",
        })
        self.assertIn("new_password1", resp.context["form"].errors)


class TwoFactorTests(BlinkTestCase):
    def setUp(self):
        self.user = self.make_user("nour")

    def enable_2fa(self):
        self.client.force_login(self.user)
        self.client.get(reverse("accounts:two_factor_setup"))
        secret = self.client.session[two_factor.SESSION_SETUP_SECRET]
        resp = self.client.post(reverse("accounts:two_factor_setup"), {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(resp, reverse("accounts:security"), fetch_redirect_response=False)
        codes = self.client.get(reverse("accounts:security")).context["recovery_codes"]
        self.client.logout()
        return secret, codes

    def login_password(self, next_url=""):
        data = {"username": "nour", "password": PASSWORD}
        if next_url:
            data["next"] = next_url
        return self.client.post(reverse("accounts:login"), data)

    def test_setup_requires_valid_code(self):
        self.client.force_login(self.user)
        self.client.get(reverse("accounts:two_factor_setup"))
        resp = self.client.post(reverse("accounts:two_factor_setup"), {"code": "000000"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.user.two_factor_enabled)

    def test_setup_shows_recovery_codes_once(self):
        _, codes = self.enable_2fa()
        self.assertEqual(len(codes), two_factor.RECOVERY_CODE_COUNT)
        self.assertTrue(self.user.two_factor_enabled)
        self.client.force_login(self.user)
        self.assertIsNone(self.client.get(reverse("accounts:security")).context["recovery_codes"])

    def test_login_requires_code(self):
        secret, _ = self.enable_2fa()
        resp = self.login_password(next_url="/posts/explorer/")
        self.assertRedirects(resp, reverse("accounts:login_2fa"))
        self.assertNotIn("_auth_user_id", self.client.session)
        # Une page protégée renvoie toujours vers la connexion.
        self.assertEqual(self.client.get(reverse("accounts:security")).status_code, 302)

        # Code déjà utilisé lors de l'activation (même fenêtre de 30 s) : refusé (anti-rejeu).
        device = TwoFactorDevice.objects.get(user=self.user)
        device.last_used_step = 0
        device.save()
        resp = self.client.post(reverse("accounts:login_2fa"), {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(resp, "/posts/explorer/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_totp_code_cannot_be_replayed(self):
        secret, _ = self.enable_2fa()
        self.login_password()
        # Le code courant a déjà servi à l'activation.
        resp = self.client.post(reverse("accounts:login_2fa"), {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_recovery_code_works_once(self):
        _, codes = self.enable_2fa()
        self.login_password()
        resp = self.client.post(reverse("accounts:login_2fa"), {"code": codes[0].upper()})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.client.logout()
        self.login_password()
        resp = self.client.post(reverse("accounts:login_2fa"), {"code": codes[0]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(TwoFactorDevice.objects.get(user=self.user).recovery_codes), len(codes) - 1)

    def test_too_many_wrong_codes_restart_login(self):
        self.enable_2fa()
        self.login_password()
        for _ in range(4):
            self.assertEqual(self.client.post(reverse("accounts:login_2fa"), {"code": "111111"}).status_code, 200)
        resp = self.client.post(reverse("accounts:login_2fa"), {"code": "111111"})
        self.assertRedirects(resp, reverse("accounts:login"))
        self.assertRedirects(self.client.get(reverse("accounts:login_2fa")), reverse("accounts:login"))

    def test_verification_page_needs_password_step(self):
        self.assertRedirects(self.client.get(reverse("accounts:login_2fa")), reverse("accounts:login"))

    def test_disable_requires_password_and_code(self):
        _, codes = self.enable_2fa()
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:two_factor_disable"), {"password": "faux", "code": codes[0]})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.user.two_factor_enabled)
        # Un mot de passe faux ne consomme pas le code de secours.
        self.assertEqual(len(TwoFactorDevice.objects.get(user=self.user).recovery_codes), len(codes))
        resp = self.client.post(reverse("accounts:two_factor_disable"), {"password": PASSWORD, "code": codes[0]})
        self.assertRedirects(resp, reverse("accounts:security"))
        self.assertFalse(self.user.two_factor_enabled)

    def test_regenerate_recovery_codes(self):
        _, codes = self.enable_2fa()
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:two_factor_codes"), {"password": PASSWORD, "code": codes[0]})
        self.assertRedirects(resp, reverse("accounts:security"), fetch_redirect_response=False)
        new_codes = self.client.get(reverse("accounts:security")).context["recovery_codes"]
        self.assertEqual(len(new_codes), two_factor.RECOVERY_CODE_COUNT)
        self.assertFalse(set(new_codes) & set(codes))

    def test_admin_login_goes_through_blink_login(self):
        resp = self.client.get("/admin/login/?next=/admin/")
        self.assertRedirects(resp, f"{reverse('accounts:login')}?next=/admin/", fetch_redirect_response=False)
        resp = self.client.get("/admin/login/?next=https://evil.example/")
        self.assertNotIn("evil", resp["Location"])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/admin/login/").status_code, 403)

    def test_drf_login_redirects_to_blink_login(self):
        resp = self.client.get("/api/auth/login/?next=/api/")
        self.assertRedirects(resp, f"{reverse('accounts:login')}?next=/api/", fetch_redirect_response=False)

    def test_api_token_requires_otp(self):
        _, codes = self.enable_2fa()
        url = reverse("token")
        resp = self.client.post(url, {"username": "nour", "password": PASSWORD})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("otp", resp.json())
        resp = self.client.post(url, {"username": "nour", "password": PASSWORD, "otp": "000000"})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(url, {"username": "nour", "password": PASSWORD, "otp": codes[1]})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())

    def test_api_token_without_2fa(self):
        resp = self.client.post(reverse("token"), {"username": "nour", "password": PASSWORD})
        self.assertEqual(resp.status_code, 200)


class ServerSideValidationTests(BlinkTestCase):
    def signup(self, **overrides):
        data = {
            "username": "nouveau", "email": "nouveau@test.tn", "first_name": "Nour", "last_name": "Ben Ali",
            "password1": "UnMotDePasse!42", "password2": "UnMotDePasse!42", **overrides,
        }
        return self.client.post(reverse("accounts:signup"), data)

    def test_signup_username_rules(self):
        self.make_user("sami")
        cases = ["ab", "avec espace", "é-accent", ".point", "admin", "SAMI", "a" * 31, "mail@test.tn"]
        for username in cases:
            resp = self.signup(username=username)
            self.assertEqual(resp.status_code, 200, username)
            self.assertIn("username", resp.context["form"].errors, username)

    def test_signup_name_and_password_rules(self):
        resp = self.signup(first_name="R2D2", password1="nouveau123", password2="nouveau123")
        errors = resp.context["form"].errors
        self.assertIn("first_name", errors)
        self.assertIn("password2", errors)
        resp = self.signup(email="")
        self.assertIn("email", resp.context["form"].errors)

    def test_signup_valid_with_accents(self):
        resp = self.signup(first_name="Éloïse", last_name="D'Arc-Ben Saïd")
        self.assertRedirects(resp, reverse("accounts:edit"))

    def test_login_shows_required_errors(self):
        resp = self.client.post(reverse("accounts:login"), {"username": "", "password": ""})
        self.assertContains(resp, "Saisis ton e-mail ou ton nom d&#x27;utilisateur.")

    def test_profile_birth_date_and_city(self):
        user = self.make_user("lina")
        self.client.force_login(user)
        base = {"first_name": "Lina", "last_name": "M", "email": "lina@test.tn", "bio": ""}
        future = date(date.today().year + 1, 1, 1).isoformat()
        for birth, ville, field in ((future, "Tunis", "date_naissance"), ("2024-01-01", "Tunis", "date_naissance"),
                                     ("2000-01-01", "<script>", "ville")):
            resp = self.client.post(reverse("accounts:edit"), {**base, "date_naissance": birth, "ville": ville})
            self.assertEqual(resp.status_code, 200)
            self.assertIn(field, resp.context["profile_form"].errors)

    def test_report_other_requires_details(self):
        author, reporter = self.make_user("nour"), self.make_user("sami")
        post = Post.objects.create(auteur=author, image=make_image())
        self.client.force_login(reporter)
        resp = self.client.post(reverse("posts:report", args=[post.pk]), {"motif": "autre", "details": "  "})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Report.objects.count(), 0)
        self.client.post(reverse("posts:report", args=[post.pk]), {"motif": "autre", "details": "Contenu trompeur"})
        self.assertEqual(Report.objects.count(), 1)

    def test_post_hashtags_are_normalized(self):
        author = self.make_user("nour")
        post = Post.objects.create(auteur=author, image=make_image())
        self.client.force_login(author)
        self.client.post(reverse("posts:update", args=[post.pk]), {
            "caption": "  Plage  ", "hashtags_ia": "#Été, plage #ÉTÉ ;;; #!!!", "visibilite": "public",
        })
        post.refresh_from_db()
        self.assertEqual(post.hashtags_ia, "#ete #plage")
        self.assertEqual(post.caption, "Plage")

    def test_non_image_upload_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        user = self.make_user("nour")
        self.client.force_login(user)
        fake = SimpleUploadedFile("photo.jpg", b"pas une image", content_type="image/jpeg")
        resp = self.client.post(reverse("posts:create"), {"image": fake, "caption": "test", "visibilite": "public"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("image", resp.context["form"].errors)
        self.assertFalse(user.posts.exists())
