import re

from django import forms

from core.models import Report
from core.validators import validate_audio_file, validate_image_format

from .ai import clean_hashtags
from .models import Comment, Post

MAX_HASHTAGS = 15


def clean_hashtag_field(value):
    """« #Été, plage  #été » → « #ete #plage » (sans doublons, sans caractères spéciaux)."""
    raw = [t for t in re.split(r"[\s,;]+", value or "") if t.strip("#")]
    tags = clean_hashtags(raw, limit=MAX_HASHTAGS + 1)
    if len(tags) > MAX_HASHTAGS:
        raise forms.ValidationError(f"{MAX_HASHTAGS} hashtags maximum.")
    return " ".join(f"#{t}" for t in tags)


class PostForm(forms.ModelForm):
    """Nouveau post : photo + légende (+ résultat IA) + message vocal optionnel."""

    audio = forms.FileField(required=False, validators=[validate_audio_file], widget=forms.ClearableFileInput(
        attrs={"accept": "audio/*", "class": "hidden", "data-recorder-input": ""}
    ))
    audio_duree = forms.IntegerField(required=False, min_value=0, max_value=3600, widget=forms.HiddenInput(
        attrs={"data-recorder-duration": ""}
    ))

    class Meta:
        model = Post
        fields = ("image", "caption", "caption_ia", "caption_style", "hashtags_ia", "visibilite")
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*", "data-image-input": ""}),
            "caption": forms.Textarea(attrs={"rows": 3, "placeholder": "Écris une légende… ou laisse l'IA le faire ✨"}),
            "caption_ia": forms.HiddenInput(),
            "caption_style": forms.HiddenInput(),
            "hashtags_ia": forms.HiddenInput(),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        validate_image_format(image)
        return image

    def clean_caption(self):
        return (self.cleaned_data.get("caption") or "").strip()

    def clean_caption_ia(self):
        return (self.cleaned_data.get("caption_ia") or "").strip()[:2200] or None

    def clean_hashtags_ia(self):
        return clean_hashtag_field(self.cleaned_data.get("hashtags_ia")) or None


class PostUpdateForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ("caption", "hashtags_ia", "visibilite")
        labels = {"hashtags_ia": "Hashtags"}
        widgets = {
            "caption": forms.Textarea(attrs={"rows": 4}),
            "hashtags_ia": forms.TextInput(attrs={"placeholder": "#goldenhour #entreamis"}),
        }

    def clean_caption(self):
        return (self.cleaned_data.get("caption") or "").strip()

    def clean_hashtags_ia(self):
        return clean_hashtag_field(self.cleaned_data.get("hashtags_ia")) or None


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("contenu",)
        labels = {"contenu": ""}
        widgets = {"contenu": forms.TextInput(attrs={"placeholder": "Ajouter un commentaire", "autocomplete": "off"})}


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ('motif', 'details')
        widgets = {
            'motif': forms.Select(attrs={'class': 'w-full'}),
            'details': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Précisions (optionnel)'}),
        }

    def clean(self):
        cleaned = super().clean()
        details = (cleaned.get("details") or "").strip()
        cleaned["details"] = details
        if cleaned.get("motif") == Report.Motif.AUTRE and len(details) < 10:
            self.add_error("details", "Explique le problème en quelques mots (10 caractères minimum) quand tu choisis « Autre ».")
        return cleaned
