from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Notification, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post_thumb", "motif", "auteur", "post_auteur", "traite", "date")
    list_filter = ("traite", "motif")
    search_fields = ("details", "post__caption", "auteur__username")
    list_editable = ("traite",)
    actions = ["masquer_posts", "classer_sans_suite"]

    @admin.display(description="Publication")
    def post_thumb(self, obj):
        return format_html(
            '<a href="{}"><img src="{}" style="width:48px;height:48px;object-fit:cover;border-radius:8px"></a>',
            reverse("admin:posts_post_change", args=[obj.post_id]), obj.post.image.url,
        )

    @admin.display(description="Auteur du post")
    def post_auteur(self, obj):
        return obj.post.auteur

    @admin.action(description="Masquer les publications signalées")
    def masquer_posts(self, request, queryset):
        from posts.models import Post

        Post.objects.filter(reports__in=queryset).update(est_masque=True)
        queryset.update(traite=True)
        self.message_user(request, "Publications masquées et signalements traités.")

    @admin.action(description="Classer sans suite")
    def classer_sans_suite(self, request, queryset):
        self.message_user(request, f"{queryset.update(traite=True)} signalement(s) classé(s).")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "type", "message", "lu", "date")
    list_filter = ("type", "lu")
    search_fields = ("message", "destinataire__username")
