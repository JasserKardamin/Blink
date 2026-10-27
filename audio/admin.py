from django.contrib import admin
from django.utils.html import format_html

from core.tasks import run_async

from .models import AudioComment, AudioPost, Transcription
from .services import transcribe_by_id


def audio_player(file):
    return format_html('<audio controls preload="none" src="{}" style="height:32px"></audio>', file.url) if file else "—"


@admin.register(AudioPost)
class AudioPostAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "player", "duree", "post", "statut_transcription", "date")
    list_filter = ("transcription__statut", "date")
    search_fields = ("description", "user__username", "transcription__texte")
    actions = ["retranscrire"]

    @admin.display(description="Écouter")
    def player(self, obj):
        return audio_player(obj.fichier_audio)

    @admin.display(description="Transcription")
    def statut_transcription(self, obj):
        t = getattr(obj, "transcription", None)
        return t.get_statut_display() if t else "—"

    @admin.action(description="Relancer la transcription IA")
    def retranscrire(self, request, queryset):
        for obj in queryset:
            run_async(transcribe_by_id, "post", obj.pk)
        self.message_user(request, f"{queryset.count()} transcription(s) relancée(s).")


@admin.register(AudioComment)
class AudioCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "post", "player", "duree", "date")
    search_fields = ("user__username", "transcription__texte")

    @admin.display(description="Écouter")
    def player(self, obj):
        return audio_player(obj.fichier_audio)


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "statut", "langue", "moteur", "extrait", "erreur", "date")
    list_filter = ("statut", "langue", "moteur")
    search_fields = ("texte",)

    @admin.display(description="Texte")
    def extrait(self, obj):
        return obj.texte[:80]
