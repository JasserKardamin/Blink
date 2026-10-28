from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import PersonalNote, Profile, User


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")
        labels = {"username": "Nom d'utilisateur", "first_name": "Prénom", "last_name": "Nom"}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="E-mail ou nom d'utilisateur",
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Email", "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Mot de passe", strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Mot de passe", "autocomplete": "current-password"}),
    )


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "bio", "photo_profil")
        labels = {"first_name": "Prénom", "last_name": "Nom"}
        widgets = {"bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Parle un peu de toi…"})}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar", "date_naissance", "ville")
        widgets = {"date_naissance": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class PersonalNoteForm(forms.ModelForm):
    class Meta:
        model = PersonalNote
        fields = ("friend", "contenu")
        labels = {"friend": "Ami(e)", "contenu": "Note"}
        widgets = {
            "friend": forms.Select(attrs={"class": "w-full"}),
            "contenu": forms.Textarea(attrs={"rows": 5, "maxlength": 2000, "placeholder": "Note personnelle…"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        friend_ids = list(user.friends().values_list("pk", flat=True))
        if self.instance.pk:
            friend_ids.append(self.instance.friend_id)
            self.fields["friend"].disabled = True
        self.fields["friend"].queryset = User.objects.filter(pk__in=friend_ids).order_by("username")

    def clean_friend(self):
        friend = self.cleaned_data["friend"]
        if not self.instance.pk and not self.user.is_friend(friend):
            raise forms.ValidationError("Tu peux créer une note uniquement pour un(e) ami(e).")
        return friend
