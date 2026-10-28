from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.urls import reverse

from core.models import Notification, Report
from core.testing import BlinkTestCase, make_image
from posts.models import Comment, Post


class CoreViewTests(BlinkTestCase):
    def setUp(self):
        self.nour = self.make_user("nour")

    def test_landing_for_visitors(self):
        Post.objects.create(auteur=self.nour, image=make_image(), visibilite="public")
        resp = self.client.get("/")
        self.assertTemplateUsed(resp, "core/landing.html")
        self.assertContains(resp, "L'IA fait le reste")

    def test_feed_for_users(self):
        self.client.force_login(self.nour)
        Post.objects.create(auteur=self.nour, image=make_image(), caption="Mon post #blink")
        resp = self.client.get("/")
        self.assertTemplateUsed(resp, "core/feed.html")
        self.assertContains(resp, 'href="/posts/tag/blink/"')

    def test_notifications_marked_read(self):
        Notification.objects.create(destinataire=self.nour, type="ia", message="Coucou")
        self.client.force_login(self.nour)
        resp = self.client.get(reverse("core:notifications"))
        self.assertContains(resp, "Coucou")
        self.assertFalse(Notification.objects.filter(lu=False).exists())

    def test_search(self):
        Post.objects.create(auteur=self.nour, image=make_image(), caption="Plage au soleil")
        resp = self.client.get(reverse("core:search"), {"q": "nour"})
        self.assertIn(self.nour, list(resp.context["users"]))
        resp = self.client.get(reverse("core:search"), {"q": "soleil"})
        self.assertEqual(len(resp.context["posts"]), 1)

    def test_admin_dashboard_and_moderation(self):
        admin = self.make_user("admin", is_staff=True, is_superuser=True)
        post = Post.objects.create(auteur=self.nour, image=make_image())
        report = Report.objects.create(auteur=admin, post=post, motif="spam")
        self.client.force_login(admin)
        resp = self.client.get(reverse("admin:index"))
        self.assertContains(resp, "Tableau de bord Blink")
        self.assertContains(resp, "Signalements à traiter")
        resp = self.client.post(reverse("admin:core_report_changelist"), {
            "action": "approuver_et_masquer", "_selected_action": [report.pk],
        })
        post.refresh_from_db()
        report.refresh_from_db()
        self.assertTrue(post.est_masque and report.traite and report.statut == Report.Statut.APPROUVE)


class ReportAPITests(BlinkTestCase):
    def setUp(self):
        self.nour = self.make_user("nour")
        self.sami = self.make_user("sami")
        self.admin = self.make_user("admin_user", is_staff=True)
        self.post = Post.objects.create(auteur=self.nour, image=make_image(), caption="Offensive content")
        self.comment = Comment.objects.create(post=self.post, user=self.nour, contenu="Spam comment")

    def test_create_report_on_post(self):
        self.client.force_login(self.sami)
        res = self.client.post(
            "/api/reports/",
            {"post": self.post.pk, "motif": "spam", "details": "Too many ads."},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["motif"], "spam")
        self.assertEqual(Report.objects.filter(auteur=self.sami, post=self.post).count(), 1)

    def test_cannot_report_own_content(self):
        self.client.force_login(self.nour)
        res = self.client.post(
            "/api/reports/",
            {"post": self.post.pk, "motif": "spam"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_staff_moderation_resolve_approve_and_mask(self):
        report = Report.objects.create(auteur=self.sami, post=self.post, motif="haine")

        # Non-staff cannot resolve
        self.client.force_login(self.sami)
        res = self.client.patch(
            f"/api/reports/{report.pk}/resolve/",
            {"statut": "approuve", "action_prise": "masquer", "notes_moderation": "Violates TOS"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

        # Staff resolves
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/reports/{report.pk}/resolve/",
            {"statut": "approuve", "action_prise": "masquer", "notes_moderation": "Violates TOS"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        self.post.refresh_from_db()
        report.refresh_from_db()
        self.assertTrue(self.post.est_masque)
        self.assertEqual(report.statut, Report.Statut.APPROUVE)
        self.assertEqual(report.moderateur, self.admin)
        # Notifications sent to both parties
        self.assertTrue(Notification.objects.filter(destinataire=self.nour).exists())
        self.assertTrue(Notification.objects.filter(destinataire=self.sami).exists())

    def test_staff_moderation_resolve_delete_comment(self):
        report = Report.objects.create(auteur=self.sami, comment=self.comment, motif="spam")
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/reports/{report.pk}/resolve/",
            {"statut": "approuve", "action_prise": "supprimer"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Comment.objects.filter(pk=self.comment.pk).exists())


class TemplateTagTests(BlinkTestCase):
    def render(self, src, **ctx):
        return Template("{% load blink_tags %}" + src).render(Context(ctx))

    def test_hashtagify_escapes_and_links(self):
        out = self.render("{{ t|hashtagify }}", t="<b>Salut</b> #été @nour")
        self.assertIn("&lt;b&gt;", out)
        self.assertIn('href="/posts/tag/%C3%A9t%C3%A9/"', out)
        self.assertIn('href="/comptes/u/nour/"', out)

    def test_duration_and_avatar(self):
        self.assertEqual(self.render("{{ 75|duration }}"), "1:15")
        user = self.make_user("sami")
        self.assertIn(">S<", self.render("{% avatar u 'sm' %}", u=user).replace("\n", "").replace(" ", ""))
        self.assertEqual(self.render("{{ u.is_authenticated }}", u=AnonymousUser()), "False")
