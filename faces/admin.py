from django.contrib import admin
from django.utils.html import format_html

from .models import DetectedFace, FaceEncoding, TagSuggestion


def thumb(field):
    return format_html('<img src="{}" style="width:48px;height:48px;object-fit:cover;border-radius:50%">', field.url) if field else "—"


@admin.register(FaceEncoding)
class FaceEncodingAdmin(admin.ModelAdmin):
    list_display = ("user", "reference", "dimensions", "date")
    search_fields = ("user__username",)
    readonly_fields = ("vecteur_encoding",)

    @admin.display(description="Référence")
    def reference(self, obj):
        return thumb(obj.photo_reference)

    @admin.display(description="Dimensions")
    def dimensions(self, obj):
        return len(obj.vecteur_encoding or [])


class TagSuggestionInline(admin.TabularInline):
    model = TagSuggestion
    extra = 0


@admin.register(DetectedFace)
class DetectedFaceAdmin(admin.ModelAdmin):
    list_display = ("id", "visage", "post", "user_identifie", "confiance", "date")
    list_filter = ("date",)
    inlines = [TagSuggestionInline]
    readonly_fields = ("encoding_detecte",)

    @admin.display(description="Visage")
    def visage(self, obj):
        return thumb(obj.image_source)


@admin.register(TagSuggestion)
class TagSuggestionAdmin(admin.ModelAdmin):
    list_display = ("user_suggere", "detected_face", "statut", "auto", "date")
    list_filter = ("statut", "auto")
