import re

from django import forms

from .models import AudioComment, AudioPost, Transcription


class AudioPostForm(forms.ModelForm):
    class Meta:
        model = AudioPost
        fields = ("fichier_audio", "description", "duree")
        labels = {"fichier_audio": "Message vocal"}
        widgets = {
            "fichier_audio": forms.ClearableFileInput(attrs={"accept": "audio/*", "class": "hidden", "data-recorder-input": ""}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "De quoi parle ton vocal ?"}),
            "duree": forms.HiddenInput(attrs={"data-recorder-duration": ""}),
        }

    def clean_duree(self):
        return min(max(self.cleaned_data.get("duree") or 0, 0), 3600)

    def clean_fichier_audio(self):
        audio = self.cleaned_data.get("fichier_audio")
        if not audio:
            raise forms.ValidationError("Veuillez sélectionner ou enregistrer un fichier audio.")
        return audio


class AudioPostUpdateForm(forms.ModelForm):
    """Formulaire de modification de la description d'un vocal."""

    class Meta:
        model = AudioPost
        fields = ("description",)
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Modifier la description de ton vocal..."}),
        }

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()


class AudioCommentForm(forms.ModelForm):
    class Meta:
        model = AudioComment
        fields = ("fichier_audio", "duree")
        widgets = {"duree": forms.HiddenInput()}

    def clean_duree(self):
        return min(max(self.cleaned_data.get("duree") or 0, 0), 3600)

    def clean_fichier_audio(self):
        audio = self.cleaned_data.get("fichier_audio")
        if not audio:
            raise forms.ValidationError("Le fichier audio du commentaire ne peut pas être vide.")
        return audio


class TranscriptionForm(forms.ModelForm):
    class Meta:
        model = Transcription
        fields = ("texte", "langue")
        widgets = {"texte": forms.Textarea(attrs={"rows": 5})}

    def clean_texte(self):
        texte = (self.cleaned_data.get("texte") or "").strip()
        if not texte:
            raise forms.ValidationError("La transcription ne peut pas être vide.")
        return texte

    def clean_langue(self):
        lang = (self.cleaned_data.get("langue") or "").strip().lower()
        if lang and not re.fullmatch(r"[a-z]{2,3}(-[a-z]{2})?", lang):
            raise forms.ValidationError("Code de langue invalide (ex. : fr, en, ar, fr-fr).")
        return lang
