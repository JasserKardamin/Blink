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


class AudioCommentForm(forms.ModelForm):
    class Meta:
        model = AudioComment
        fields = ("fichier_audio", "duree")
        widgets = {"duree": forms.HiddenInput()}

    def clean_duree(self):
        return min(max(self.cleaned_data.get("duree") or 0, 0), 3600)


class TranscriptionForm(forms.ModelForm):
    class Meta:
        model = Transcription
        fields = ("texte", "langue")
        widgets = {"texte": forms.Textarea(attrs={"rows": 5})}
