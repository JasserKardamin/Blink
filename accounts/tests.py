from django.urls import reverse

from accounts.models import Friendship, PersonalNote, User
from core.models import Notification
from core.testing import BlinkTestCase


class AuthTests(BlinkTestCase):
    def test_signup_creates_profile_and_logs_in(self):
        resp = self.client.post(reverse("accounts:signup"), {
            "username": "nour", "email": "Nour@Test.tn", "first_name": "Nour", "last_name": "B",
            "password1": "UnMotDePasse!42", "password2": "UnMotDePasse!42",
        })
        self.assertRedirects(resp, reverse("accounts:edit"))
        user = User.objects.get(username="nour")
        self.assertEqual(user.email, "nour@test.tn")
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_with_email_or_username(self):
        self.make_user("sami")
        for identifier in ("sami", "sami@test.tn", "SAMI@test.tn"):
            self.client.logout()
            resp = self.client.post(reverse("accounts:login"), {"username": identifier, "password": "motdepasse123"})
            self.assertRedirects(resp, reverse("core:home"), msg_prefix=identifier)

    def test_duplicate_email_rejected(self):
        self.make_user("sami")
        resp = self.client.post(reverse("accounts:signup"), {
            "username": "autre", "email": "sami@test.tn", "password1": "UnMotDePasse!42", "password2": "UnMotDePasse!42",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "existe déjà")

    def test_profile_update(self):
        user = self.make_user("lina")
        self.client.force_login(user)
        resp = self.client.post(reverse("accounts:edit"), {
            "first_name": "Lina", "last_name": "M", "email": "lina@test.tn", "bio": "Bonjour #blink",
            "ville": "Bizerte", "date_naissance": "2001-05-04",
        })
        self.assertRedirects(resp, user.get_absolute_url())
        user.refresh_from_db()
        self.assertEqual(user.bio, "Bonjour #blink")
        self.assertEqual(user.profile.ville, "Bizerte")


class FriendshipTests(BlinkTestCase):
    def setUp(self):
        self.nour, self.sami = self.make_user("nour"), self.make_user("sami")

    def test_request_accept_flow(self):
        self.client.force_login(self.nour)
        self.client.post(reverse("accounts:friend_request", args=["sami"]))
        fr = Friendship.objects.get(user_from=self.nour, user_to=self.sami)
        self.assertEqual(fr.statut, Friendship.Statut.EN_ATTENTE)
        self.assertTrue(Notification.objects.filter(destinataire=self.sami, type="ami").exists())

        self.client.force_login(self.sami)
        self.client.post(reverse("accounts:friend_respond", args=[fr.pk, "accepter"]))
        fr.refresh_from_db()
        self.assertEqual(fr.statut, Friendship.Statut.ACCEPTE)
        self.assertTrue(self.nour.is_friend(self.sami))
        self.assertIn(self.sami, self.nour.friends())
        self.assertTrue(self.nour.is_following(self.sami) and self.sami.is_following(self.nour))

    def test_reverse_request_accepts(self):
        Friendship.objects.create(user_from=self.sami, user_to=self.nour)
        self.client.force_login(self.nour)
        self.client.post(reverse("accounts:friend_request", args=["sami"]))
        self.assertTrue(self.nour.is_friend(self.sami))
        self.assertEqual(Friendship.objects.count(), 1)

    def test_only_recipient_can_respond(self):
        fr = Friendship.objects.create(user_from=self.nour, user_to=self.sami)
        self.client.force_login(self.nour)
        resp = self.client.post(reverse("accounts:friend_respond", args=[fr.pk, "accepter"]))
        self.assertEqual(resp.status_code, 404)

    def test_remove_friend(self):
        self.befriend(self.nour, self.sami)
        self.client.force_login(self.sami)
        self.client.post(reverse("accounts:friend_remove", args=["nour"]))
        self.assertFalse(self.nour.is_friend(self.sami))

    def test_follow_toggle(self):
        self.client.force_login(self.nour)
        self.client.post(reverse("accounts:follow", args=["sami"]))
        self.assertTrue(self.nour.is_following(self.sami))
        self.client.post(reverse("accounts:follow", args=["sami"]))
        self.assertFalse(self.nour.is_following(self.sami))


class PersonalNoteTests(BlinkTestCase):
    def setUp(self):
        self.nour = self.make_user("nour")
        self.sami = self.make_user("sami")
        self.befriend(self.nour, self.sami)
        self.client.force_login(self.nour)

    def test_create_list_update_and_delete_private_note(self):
        create_url = reverse("accounts:personal_note_create")
        response = self.client.post(create_url, {"friend": self.sami.pk, "contenu": "Aime le café"})
        self.assertRedirects(response, reverse("accounts:personal_notes"))
        note = PersonalNote.objects.get(owner=self.nour, friend=self.sami)

        response = self.client.get(reverse("accounts:personal_notes"))
        self.assertContains(response, "Aime le café")
        self.assertContains(response, "sami")

        response = self.client.post(
            reverse("accounts:personal_note_edit", args=[note.pk]),
            {"friend": self.sami.pk, "contenu": "Préfère le thé"},
        )
        self.assertRedirects(response, reverse("accounts:personal_notes"))
        note.refresh_from_db()
        self.assertEqual(note.contenu, "Préfère le thé")

        response = self.client.post(reverse("accounts:personal_note_delete", args=[note.pk]))
        self.assertRedirects(response, reverse("accounts:personal_notes"))
        self.assertFalse(PersonalNote.objects.filter(pk=note.pk).exists())

    def test_notes_are_private_and_other_users_cannot_modify_them(self):
        note = PersonalNote.objects.create(owner=self.nour, friend=self.sami, contenu="Secret")

        self.client.force_login(self.sami)
        self.assertNotContains(self.client.get(reverse("accounts:personal_notes")), "Secret")
        self.assertEqual(self.client.get(reverse("accounts:personal_note_edit", args=[note.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("accounts:personal_note_delete", args=[note.pk])).status_code, 404)

    def test_note_can_only_be_created_for_a_friend(self):
        outsider = self.make_user("lina")
        response = self.client.post(
            reverse("accounts:personal_note_create"),
            {"friend": outsider.pk, "contenu": "Not a friend"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PersonalNote.objects.filter(owner=self.nour).exists())
