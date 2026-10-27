from django import forms
from django.db.models import Q

from .models import AIPromptTemplate, GeneratedImage, ImageFilter, Style


class GenerateForm(forms.ModelForm):
    """Paramètres d'une génération (filtre IA ou image dérivée)."""

    class Meta:
        model = GeneratedImage
        fields = ("type", "style", "filtre", "template")
        labels = {"filtre": "Filtre personnalisé (optionnel)", "template": "Modèle de prompt (optionnel)"}
        widgets = {"type": forms.RadioSelect, "style": forms.RadioSelect}

    def __init__(self, *args, user=None, avatar=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["filtre"].queryset = ImageFilter.objects.filter(Q(user__isnull=True) | Q(user=user))
        self.fields["template"].queryset = AIPromptTemplate.objects.filter(
            user=user, type__in=[AIPromptTemplate.Type.IMAGE, AIPromptTemplate.Type.FILTRE]
        )
        self.fields["filtre"].required = False
        self.fields["template"].required = False
        self.fields["filtre"].empty_label = "Aucun — utiliser le style choisi"
        self.fields["template"].empty_label = "Aucun — prompt automatique"
        if avatar:
            del self.fields["type"]
        else:
            self.fields["type"].choices = [
                (GeneratedImage.Type.FILTRE, "Filtre IA (instantané, fidèle à la photo)"),
                (GeneratedImage.Type.DERIVEE, "Image artistique dérivée (Stable Diffusion)"),
            ]

    def clean(self):
        data = super().clean()
        filtre = data.get("filtre")
        if filtre:
            data["style"] = filtre.base_style
        return data


class ImageFilterForm(forms.ModelForm):
    base = forms.ChoiceField(label="Style de base", choices=Style.choices)
    intensite = forms.FloatField(label="Intensité", min_value=0.1, max_value=1.0, initial=1.0,
                                 widget=forms.NumberInput(attrs={"step": "0.1", "type": "range", "min": "0.1", "max": "1"}))
    saturation = forms.FloatField(min_value=0.0, max_value=2.5, initial=1.0,
                                  widget=forms.NumberInput(attrs={"step": "0.1", "type": "range", "min": "0", "max": "2.5"}))
    contraste = forms.FloatField(min_value=0.5, max_value=2.0, initial=1.0,
                                 widget=forms.NumberInput(attrs={"step": "0.1", "type": "range", "min": "0.5", "max": "2"}))

    class Meta:
        model = ImageFilter
        fields = ("nom", "description", "preview")
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        params = self.instance.parametres or {}
        for key in ("base", "intensite", "saturation", "contraste"):
            if key in params:
                self.fields[key].initial = params[key]

    def save(self, commit=True):
        self.instance.parametres = {
            "base": self.cleaned_data["base"],
            "intensite": self.cleaned_data["intensite"],
            "saturation": self.cleaned_data["saturation"],
            "contraste": self.cleaned_data["contraste"],
        }
        return super().save(commit)


class PromptTemplateForm(forms.ModelForm):
    class Meta:
        model = AIPromptTemplate
        fields = ("nom", "type", "template_prompt")
        widgets = {
            "template_prompt": forms.Textarea(attrs={
                "rows": 4, "placeholder": "{description}, {style}, golden hour, cinematic lighting",
            })
        }
