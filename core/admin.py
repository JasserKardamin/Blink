from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Notification, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "target_preview", "motif", "statut", "action_prise", "auteur", "moderateur", "date")
    list_filter = ("statut", "motif", "action_prise", "traite")
    search_fields = ("details", "post__caption", "auteur__username", "notes_moderation")
    readonly_fields = ("date", "date_traitement")
    actions = ["approuver_et_masquer", "rejeter_signalement"]

    @admin.display(description="Cible")
    def target_preview(self, obj):
        if obj.post:
            thumb = obj.post.image.url if obj.post.image else ""
            return format_html(
                '<a href="{}">Post #{} {}</a>',
                reverse("admin:posts_post_change", args=[obj.post_id]),
                obj.post_id,
                f'(par {obj.post.auteur})',
            )
        elif obj.comment:
            return format_html("Commentaire #{}: {}", obj.comment_id, obj.comment.texte[:30])
        elif obj.reported_user:
            return format_html("Utilisateur: {}", obj.reported_user.username)
        return "—"

    @admin.action(description="Approuver et masquer les publications signalées")
    def approuver_et_masquer(self, request, queryset):
        from posts.models import Post
        from django.utils import timezone

        for report in queryset:
            if report.post:
                report.post.est_masque = True
                report.post.save(update_fields=["est_masque"])
                report.action_prise = Report.Action.MASQUER
            report.statut = Report.Statut.APPROUVE
            report.moderateur = request.user
            report.date_traitement = timezone.now()
            report.save()
        self.message_user(request, f"{queryset.count()} signalement(s) approuvé(s) et contenu masqué.")

    @admin.action(description="Rejeter les signalements sélectionnés")
    def rejeter_signalement(self, request, queryset):
        from django.utils import timezone

        for report in queryset:
            report.statut = Report.Statut.REJETE
            report.action_prise = Report.Action.AUCUNE
            report.moderateur = request.user
            report.date_traitement = timezone.now()
            report.save()
        self.message_user(request, f"{queryset.count()} signalement(s) rejeté(s).")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "type", "message", "lu", "date")
    list_filter = ("type", "lu")
    search_fields = ("message", "destinataire__username")
