from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models.functions import TruncDate
from django.utils import timezone


class BlinkAdminSite(admin.AdminSite):
    site_header = "Blink · Administration"
    site_title = "Blink admin"
    index_title = "Tableau de bord"
    index_template = "admin/blink_index.html"

    def login(self, request, extra_context=None):
        """Connexion via la page Blink (qui applique la double authentification)."""
        next_url = request.GET.get(REDIRECT_FIELD_NAME, "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse("admin:index", current_app=self.name)
        if request.user.is_authenticated:
            if request.user.is_active and request.user.is_staff:
                return redirect(next_url)
            raise PermissionDenied("Accès réservé à l'équipe de modération.")
        return redirect_to_login(next_url)

    def index(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "stats": self.get_stats()}
        return super().index(request, extra_context)

    def get_stats(self):
        from accounts.models import Friendship, User
        from aistudio.models import GeneratedImage
        from audio.models import AudioComment, AudioPost, Transcription
        from core.models import Report
        from faces.models import DetectedFace, TagSuggestion
        from posts.models import AIGeneration, Comment, Post, Reaction

        now = timezone.now()
        since = now - timedelta(days=13)
        per_day = dict(
            Post.objects.filter(date_creation__date__gte=since.date())
            .annotate(day=TruncDate("date_creation")).values("day").annotate(n=Count("id")).values_list("day", "n")
        )
        days = [(since + timedelta(days=i)).date() for i in range(14)]
        series = [{"day": d, "count": per_day.get(d, 0)} for d in days]
        peak = max([s["count"] for s in series] + [1])
        for s in series:
            s["pct"] = round(100 * s["count"] / peak)

        ai_by_type = dict(AIGeneration.objects.values("type").annotate(n=Count("id")).values_list("type", "n"))
        ai_by_engine = list(
            AIGeneration.objects.values("moteur").annotate(n=Count("id")).order_by("-n")[:6]
        )
        return {
            "kpis": [
                ("Utilisateurs", User.objects.count(), f"+{User.objects.filter(date_joined__gte=now - timedelta(days=7)).count()} cette semaine"),
                ("Publications", Post.objects.count(), f"{Post.objects.filter(est_masque=True).count()} masquées"),
                ("Interactions", Reaction.objects.count() + Comment.objects.count() + AudioComment.objects.count(), "réactions + commentaires"),
                ("Amitiés", Friendship.objects.filter(statut="accepte").count(), f"{Friendship.objects.filter(statut='en_attente').count()} en attente"),
            ],
            "ai": [
                ("Légendes IA", ai_by_type.get("legende", 0)),
                ("Transcriptions", Transcription.objects.filter(statut="termine").count()),
                ("Images IA", GeneratedImage.objects.filter(statut="termine").count()),
                ("Visages détectés", DetectedFace.objects.exclude(bounding_box={}).count()),
                ("Tags confirmés", TagSuggestion.objects.filter(statut="accepte").count()),
                ("Vocaux publiés", AudioPost.objects.count()),
            ],
            "ai_by_engine": ai_by_engine,
            "series": series,
            "pending_reports": Report.objects.filter(traite=False).select_related("post", "auteur")[:8],
            "pending_reports_count": Report.objects.filter(traite=False).count(),
            "transcription_errors": Transcription.objects.filter(statut="erreur").count(),
        }
