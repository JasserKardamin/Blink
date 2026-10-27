from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Profile, User


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
