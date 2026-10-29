import re
from datetime import date

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from core.validators import validate_image_format

from . import two_factor
from .models import PersonalNote, Profile, User

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)*$")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$")
CITY_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$")
RESERVED_USERNAMES = {
    "admin", "administrateur", "administrator", "root", "staff", "support", "moderateur", "moderation",
    "blink", "api", "static", "media", "comptes", "posts", "audio", "studio", "visages", "null", "none",
}
MIN_AGE = 13


def clean_person_name(value, label):
    value = " ".join((value or "").split())
    if value and not NAME_RE.match(value):
        raise forms.ValidationError(f"Le {label} ne peut contenir que des lettres, espaces, tirets ou apostrophes.")
    return value


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")
        labels = {"username": "Nom d'utilisateur", "first_name": "Prénom", "last_name": "Nom"}
        help_texts = {"username": "3 à 30 caractères : lettres, chiffres, « _ » et « . »."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not 3 <= len(username) <= 30:
            raise forms.ValidationError("Le nom d'utilisateur doit contenir entre 3 et 30 caractères.")
        if not USERNAME_RE.match(username):
            raise forms.ValidationError(
                "Utilise uniquement des lettres non accentuées, des chiffres, « _ » et « . » (pas au début ni à la fin)."
            )
        if username.lower() in RESERVED_USERNAMES:
            raise forms.ValidationError("Ce nom d'utilisateur est réservé.")
        # La connexion ignore la casse : « Sami » et « sami » ne peuvent pas coexister.
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email

    def clean_first_name(self):
        return clean_person_name(self.cleaned_data.get("first_name"), "prénom")

    def clean_last_name(self):
        return clean_person_name(self.cleaned_data.get("last_name"), "nom")


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="E-mail ou nom d'utilisateur",
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Email", "autocomplete": "username"}),
        error_messages={"required": "Saisis ton e-mail ou ton nom d'utilisateur."},
    )
    password = forms.CharField(
        label="Mot de passe", strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Mot de passe", "autocomplete": "current-password"}),
        error_messages={"required": "Saisis ton mot de passe."},
    )
    error_messages = {
        "invalid_login": "E-mail/nom d'utilisateur ou mot de passe incorrect.",
        "inactive": "Ce compte a été désactivé.",
    }


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "bio", "photo_profil")
        labels = {"first_name": "Prénom", "last_name": "Nom"}
        widgets = {"bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Parle un peu de toi…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email

    def clean_first_name(self):
        return clean_person_name(self.cleaned_data.get("first_name"), "prénom")

    def clean_last_name(self):
        return clean_person_name(self.cleaned_data.get("last_name"), "nom")

    def clean_bio(self):
        return (self.cleaned_data.get("bio") or "").strip()

    def clean_photo_profil(self):
        photo = self.cleaned_data.get("photo_profil")
        validate_image_format(photo)
        return photo


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar", "date_naissance", "ville")
        widgets = {"date_naissance": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        validate_image_format(avatar)
        return avatar

    def clean_date_naissance(self):
        birth = self.cleaned_data.get("date_naissance")
        if birth is None:
            return birth
        today = date.today()
        if birth > today:
            raise forms.ValidationError("La date de naissance ne peut pas être dans le futur.")
        if birth.year < 1900:
            raise forms.ValidationError("Saisis une date de naissance valide.")
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        if age < MIN_AGE:
            raise forms.ValidationError(f"Tu dois avoir au moins {MIN_AGE} ans pour utiliser Blink.")
        return birth

    def clean_ville(self):
        ville = " ".join((self.cleaned_data.get("ville") or "").split())
        if ville and not CITY_RE.match(ville):
            raise forms.ValidationError("Le nom de la ville ne peut contenir que des lettres, espaces, tirets ou apostrophes.")
        return ville


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

    def clean_contenu(self):
        contenu = (self.cleaned_data.get("contenu") or "").strip()
        if not contenu:
            raise forms.ValidationError("La note ne peut pas être vide.")
        return contenu


# --- Mots de passe -------------------------------------------------------------

class BlinkPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label="Adresse e-mail", max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "toi@exemple.com", "autofocus": True}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class BlinkSetPasswordForm(SetPasswordForm):
    pass


class BlinkPasswordChangeForm(PasswordChangeForm):
    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_password1")
        old = cleaned.get("old_password")
        if new and old and new == old:
            self.add_error("new_password1", "Le nouveau mot de passe doit être différent de l'actuel.")
        return cleaned


# --- Double authentification ----------------------------------------------------

def code_field(label="Code de vérification"):
    return forms.CharField(
        label=label, max_length=20, strip=True,
        widget=forms.TextInput(attrs={
            "autocomplete": "one-time-code", "inputmode": "text", "autofocus": True,
            "placeholder": "123456", "class": "text-center tracking-[0.3em] text-lg",
        }),
        error_messages={"required": "Saisis le code."},
    )


class TwoFactorSetupForm(forms.Form):
    """Confirme que l'application d'authentification est bien configurée avec le nouveau secret."""

    code = code_field("Code à 6 chiffres affiché par l'application")

    def __init__(self, *args, secret, **kwargs):
        super().__init__(*args, **kwargs)
        self.secret = secret

    def clean_code(self):
        code = self.cleaned_data["code"]
        step = two_factor.match_totp(self.secret, code)
        if step is None:
            raise forms.ValidationError("Code incorrect ou expiré. Vérifie l'heure de ton téléphone et réessaie.")
        self.step = step
        return code


class TwoFactorLoginForm(forms.Form):
    code = code_field("Code de l'application ou code de secours")

    def __init__(self, *args, device, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = device

    def clean_code(self):
        code = self.cleaned_data["code"]
        if not self.device.verify(code):
            raise forms.ValidationError("Code incorrect ou déjà utilisé.")
        return code


class TwoFactorConfirmForm(forms.Form):
    """Mot de passe + code 2FA, exigés pour désactiver la 2FA ou régénérer les codes de secours."""

    password = forms.CharField(
        label="Mot de passe actuel", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        error_messages={"required": "Saisis ton mot de passe."},
    )
    code = code_field("Code de l'application ou code de secours")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["code"].widget.attrs.pop("autofocus", None)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Mot de passe incorrect.")
        return password

    def clean(self):
        cleaned = super().clean()
        # Le code n'est vérifié (et éventuellement consommé) qu'avec un mot de passe correct.
        if "password" in cleaned and "code" in cleaned and not self.user.two_factor.verify(cleaned["code"]):
            self.add_error("code", "Code incorrect ou déjà utilisé.")
        return cleaned
