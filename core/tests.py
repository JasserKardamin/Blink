from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.urls import reverse

from core.models import Notification, Report
from core.testing import BlinkTestCase, make_image
from posts.models import Post


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
            "action": "masquer_posts", "_selected_action": [report.pk],
        })
        post.refresh_from_db()
        report.refresh_from_db()
        self.assertTrue(post.est_masque and report.traite)


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
