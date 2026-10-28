from django import forms

from core.models import Report
from core.validators import validate_audio_file

from .models import Comment, Post


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


class PostUpdateForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ("caption", "hashtags_ia", "visibilite")
        labels = {"hashtags_ia": "Hashtags"}
        widgets = {
            "caption": forms.Textarea(attrs={"rows": 4}),
            "hashtags_ia": forms.TextInput(attrs={"placeholder": "#goldenhour #entreamis"}),
        }


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
