from django.contrib import admin
from django.utils.html import format_html

from .models import AIPromptTemplate, GeneratedImage, ImageFilter


def thumb(field):
    return format_html('<img src="{}" style="width:56px;height:56px;object-fit:cover;border-radius:8px">', field.url) if field else "—"


@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    list_display = ("id", "originale", "generee", "type", "style", "modele", "statut", "user", "date")
    list_filter = ("type", "style", "statut", "modele")
    search_fields = ("prompt", "user__username")
    readonly_fields = ("date",)

    @admin.display(description="Originale")
    def originale(self, obj):
        return thumb(obj.image_originale)

    @admin.display(description="Générée")
    def generee(self, obj):
        return thumb(obj.image_generee)


@admin.register(ImageFilter)
class ImageFilterAdmin(admin.ModelAdmin):
    list_display = ("nom", "user", "parametres", "date")
    list_filter = (("user", admin.EmptyFieldListFilter),)
    search_fields = ("nom", "description")


@admin.register(AIPromptTemplate)
class AIPromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("nom", "type", "user", "date")
    list_filter = ("type",)
    search_fields = ("nom", "template_prompt")
