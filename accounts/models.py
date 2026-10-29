from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.urls import reverse

from core.validators import validate_image_size

AVATAR_COLORS = ["#8B7BFF", "#FF7A6B", "#66C5FF", "#F5B544", "#4ADE80", "#F472B6"]


class User(AbstractUser):
    """Utilisateur Blink (Gestion commune)."""

    email = models.EmailField("adresse e-mail", unique=True)
    photo_profil = models.ImageField(
        "photo de profil",
        upload_to="profils/%Y/%m/",
        blank=True,
        validators=[validate_image_size],
        help_text="Une photo nette de votre visage permet à Blink de vous reconnaître sur les photos de vos amis.",
    )
    bio = models.TextField(blank=True, max_length=500)
    following = models.ManyToManyField(
        "self", through="Follow", symmetrical=False, related_name="followers", blank=True
    )

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["username"]

    def __str__(self):
        return self.username

    def get_absolute_url(self):
        return reverse("accounts:profile", kwargs={"username": self.username})

    # --- Abonnements (diagramme de classes : follow / unfollow / is_following)
    def follow(self, user):
        if user != self:
            Follow.objects.get_or_create(follower=self, followed=user)

    def unfollow(self, user):
        Follow.objects.filter(follower=self, followed=user).delete()

    def is_following(self, user):
        return Follow.objects.filter(follower=self, followed=user).exists()

    # --- Amitiés
    def friends(self):
        accepted = Friendship.objects.filter(statut=Friendship.Statut.ACCEPTE)
        ids_to = accepted.filter(user_from=self).values_list("user_to", flat=True)
        ids_from = accepted.filter(user_to=self).values_list("user_from", flat=True)
        return User.objects.filter(Q(pk__in=ids_to) | Q(pk__in=ids_from))

    def friend_ids(self):
        return set(self.friends().values_list("pk", flat=True))

    def is_friend(self, user):
        return Friendship.objects.filter(
            Q(user_from=self, user_to=user) | Q(user_from=user, user_to=self),
            statut=Friendship.Statut.ACCEPTE,
        ).exists()

    def friendship_with(self, user):
        return Friendship.objects.filter(
            Q(user_from=self, user_to=user) | Q(user_from=user, user_to=self)
        ).first()

    @property
    def display_avatar_url(self):
        profile = getattr(self, "profile", None)
        if profile and profile.avatar:
            return profile.avatar.url
        if self.photo_profil:
            return self.photo_profil.url
        return ""

    @property
    def avatar_color(self):
        return AVATAR_COLORS[(self.pk or 0) % len(AVATAR_COLORS)]

    @property
    def initial(self):
        return (self.first_name or self.username or "?")[0].upper()

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def two_factor_enabled(self):
        return TwoFactorDevice.objects.filter(user=self).exists()


class Profile(models.Model):
    """Profil étendu (OneToOne avec User)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/", blank=True, validators=[validate_image_size],
        help_text="Avatar affiché (peut être généré par l'IA dans le Studio).",
    )
    date_naissance = models.DateField("date de naissance", null=True, blank=True)
    ville = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "profil"

    def __str__(self):
        return f"Profil de {self.user}"

    def get_avatar(self):
        return self.avatar or self.user.photo_profil or None

    def update_bio(self, text):
        self.user.bio = text
        self.user.save(update_fields=["bio"])


class Friendship(models.Model):
    """Demande d'amitié entre deux utilisateurs."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        ACCEPTE = "accepte", "Acceptée"
        REFUSE = "refuse", "Refusée"

    user_from = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_sent")
    user_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_received")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "amitié"
        verbose_name_plural = "amitiés"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user_from", "user_to"], name="unique_friendship"),
            models.CheckConstraint(condition=~Q(user_from=models.F("user_to")), name="no_self_friendship"),
        ]

    def __str__(self):
        return f"{self.user_from} → {self.user_to} ({self.get_statut_display()})"


class PersonalNote(models.Model):
    """Private note one user keeps about one of their friends."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_notes")
    friend = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notes_about")
    contenu = models.TextField(max_length=2000)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_modification"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "friend"], name="unique_personal_note_per_friend"),
            models.CheckConstraint(condition=~Q(owner=models.F("friend")), name="no_personal_note_about_self"),
        ]

    def __str__(self):
        return f"Note privée de {self.owner} sur {self.friend}"


class TwoFactorDevice(models.Model):
    """Double authentification TOTP d'un utilisateur (la ligne existe seulement si la 2FA est active)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64)
    # Empreintes SHA-256 des codes de secours encore utilisables.
    recovery_codes = models.JSONField(default=list, blank=True)
    # Dernier pas de temps accepté : un même code ne peut pas être rejoué.
    last_used_step = models.BigIntegerField(default=0)
    date_activation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "double authentification"
        verbose_name_plural = "doubles authentifications"

    def __str__(self):
        return f"2FA de {self.user}"

    def verify(self, code):
        """Valide un code TOTP ou consomme un code de secours."""
        from . import two_factor

        step = two_factor.match_totp(self.secret, code, self.last_used_step)
        if step is not None:
            self.last_used_step = step
            self.save(update_fields=["last_used_step"])
            return True
        digest = two_factor.hash_recovery_code(code)
        if digest in self.recovery_codes:
            self.recovery_codes = [c for c in self.recovery_codes if c != digest]
            self.save(update_fields=["recovery_codes"])
            return True
        return False


class Follow(models.Model):
    """Abonnement (asymétrique) d'un utilisateur à un autre."""

    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follow_links")
    followed = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follower_links")
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "abonnement"
        constraints = [models.UniqueConstraint(fields=["follower", "followed"], name="unique_follow")]

    def __str__(self):
        return f"{self.follower} suit {self.followed}"
