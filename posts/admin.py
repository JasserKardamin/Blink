from django.contrib import admin
from django.utils.html import format_html

from audio.models import AudioPost
from core.models import Report

from .models import AIGeneration, Comment, Post, Reaction


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("user", "contenu", "date")
    readonly_fields = ("date",)
    autocomplete_fields = ("user",)


class AudioPostInline(admin.TabularInline):
    model = AudioPost
    extra = 0
    fields = ("user", "fichier_audio", "duree")
    autocomplete_fields = ("user",)


class ReportInline(admin.TabularInline):
    model = Report
    extra = 0
    fields = ("auteur", "motif", "details", "traite")
    readonly_fields = ("auteur", "motif", "details")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("thumb", "auteur", "short_caption", "visibilite", "nb_reactions", "nb_reports", "est_masque", "date_creation")
    list_display_links = ("thumb", "short_caption")
    list_filter = ("visibilite", "est_masque", "caption_style", "date_creation")
    search_fields = ("caption", "caption_ia", "hashtags_ia", "auteur__username")
    date_hierarchy = "date_creation"
    readonly_fields = ("preview", "date_creation", "date_modification")
    autocomplete_fields = ("auteur",)
    inlines = [AudioPostInline, CommentInline, ReportInline]
    actions = ["masquer", "demasquer"]
    fieldsets = (
        (None, {"fields": ("auteur", "image", "preview", "caption", "visibilite", "est_masque")}),
        ("Intelligence artificielle", {"fields": ("caption_style", "caption_ia", "hashtags_ia")}),
        ("Dates", {"fields": ("date_creation", "date_modification")}),
    )

    @admin.display(description="")
    def thumb(self, obj):
        return format_html('<img src="{}" style="width:48px;height:48px;object-fit:cover;border-radius:8px">', obj.image.url) if obj.image else "—"

    @admin.display(description="Aperçu")
    def preview(self, obj):
        return format_html('<img src="{}" style="max-width:360px;border-radius:12px">', obj.image.url) if obj.image else "—"

    @admin.display(description="Légende")
    def short_caption(self, obj):
        return (obj.caption or "(sans légende)")[:60]

    @admin.display(description="Réactions")
    def nb_reactions(self, obj):
        return obj.reactions.count()

    @admin.display(description="Signalements")
    def nb_reports(self, obj):
        n = obj.reports.filter(traite=False).count()
        return format_html('<b style="color:#d9483b">{}</b>', n) if n else 0

    @admin.action(description="Masquer (modération)")
    def masquer(self, request, queryset):
        n = queryset.update(est_masque=True)
        Report.objects.filter(post__in=queryset).update(traite=True)
        self.message_user(request, f"{n} publication(s) masquée(s), signalements traités.")

    @admin.action(description="Rendre visible")
    def demasquer(self, request, queryset):
        self.message_user(request, f"{queryset.update(est_masque=False)} publication(s) visible(s).")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "post", "date")
    list_filter = ("type",)
    search_fields = ("user__username",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "contenu", "date")
    search_fields = ("contenu", "user__username")
    list_filter = ("date",)


@admin.register(AIGeneration)
class AIGenerationAdmin(admin.ModelAdmin):
    list_display = ("type", "moteur", "user", "post", "created_at")
    list_filter = ("type", "moteur")
    search_fields = ("prompt", "user__username")
    readonly_fields = ("post", "user", "type", "moteur", "prompt", "result", "created_at")

    def has_add_permission(self, request):
        return False
