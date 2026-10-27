import re

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse

from core.validators import validate_image_size

HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)


class PostQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Publications qu'un utilisateur (ou un visiteur) a le droit de voir."""
        qs = self.filter(est_masque=False)
        if not user or not user.is_authenticated:
            return qs.filter(visibilite=Post.Visibilite.PUBLIC)
        return qs.filter(
            Q(visibilite=Post.Visibilite.PUBLIC)
            | Q(auteur=user)
            | Q(visibilite=Post.Visibilite.AMIS, auteur__in=user.friends())
        )

    def feed_for(self, user):
        """Fil d'actualité : mes posts, ceux de mes amis et des comptes suivis."""
        authors = set(user.friend_ids()) | set(user.following.values_list("pk", flat=True)) | {user.pk}
        return self.visible_to(user).filter(auteur__in=authors)

    def with_stats(self, user=None):
        qs = self.select_related("auteur", "auteur__profile").prefetch_related(
            "audio_posts__transcription", "detected_faces__tag_suggestions__user_suggere"
        ).annotate(
            nb_reactions=models.Count("reactions", distinct=True),
            nb_commentaires=models.Count("comments", distinct=True) + models.Count("audio_comments", distinct=True),
        ).order_by("-date_creation")  # GROUP BY ignore Meta.ordering : on l'explicite
        if user is not None and user.is_authenticated:
            qs = qs.annotate(
                my_reaction=models.Subquery(
                    Reaction.objects.filter(post=models.OuterRef("pk"), user=user).values("type")[:1]
                )
            )
        return qs


class Post(models.Model):
    """Publication photo (Gestion 1)."""

    class Visibilite(models.TextChoices):
        PUBLIC = "public", "Public"
        AMIS = "amis", "Amis"
        PRIVE = "prive", "Privé"

    class Style(models.TextChoices):
        POETIQUE = "poetique", "Poétique"
        MARKETING = "marketing", "Marketing"
        HUMORISTIQUE = "humoristique", "Humoristique"

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts")
    image = models.ImageField(upload_to="posts/%Y/%m/", validators=[validate_image_size])
    caption = models.TextField("légende", blank=True, max_length=2200)
    caption_ia = models.TextField("légende IA", null=True, blank=True)
    caption_style = models.CharField(max_length=20, choices=Style.choices, blank=True)
    hashtags_ia = models.TextField("hashtags IA", null=True, blank=True)
    visibilite = models.CharField("visibilité", max_length=10, choices=Visibilite.choices, default=Visibilite.PUBLIC)
    est_masque = models.BooleanField("masqué par la modération", default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = "publication"
        ordering = ["-date_creation"]
        indexes = [models.Index(fields=["-date_creation"]), models.Index(fields=["visibilite", "est_masque"])]

    def __str__(self):
        return f"{self.auteur} – {self.caption[:40] or 'photo'}"

    def get_absolute_url(self):
        return reverse("posts:detail", kwargs={"pk": self.pk})

    def get_hashtags(self):
        tags = HASHTAG_RE.findall(self.caption or "")
        tags += HASHTAG_RE.findall(self.hashtags_ia or "")
        seen, result = set(), []
        for tag in tags:
            if tag.lower() not in seen:
                seen.add(tag.lower())
                result.append(tag)
        return result

    def get_likes(self):
        return self.reactions.count()

    def tagged_users(self):
        """Amis identifiés (tags acceptés) — exploite le prefetch de with_stats()."""
        users = []
        for face in self.detected_faces.all():
            for tag in face.tag_suggestions.all():
                if tag.statut == "accepte" and tag.user_suggere not in users:
                    users.append(tag.user_suggere)
        return users

    @property
    def caption_is_ai(self):
        return bool(self.caption_ia and self.caption_ia.strip() and self.caption_ia.strip() in (self.caption or ""))

    def reaction_of(self, user):
        if not user.is_authenticated:
            return None
        return self.reactions.filter(user=user).first()

    def can_view(self, user):
        return Post.objects.visible_to(user).filter(pk=self.pk).exists()

    def generate_ai(self, style=Style.POETIQUE):
        """Génère légende + hashtags avec Gemini et les enregistre (diagramme de classes)."""
        from . import ai

        result = ai.generate_caption(self.image, style=style, context=self.caption)
        self.caption_ia = result["caption"]
        self.caption_style = style
        self.hashtags_ia = " ".join(f"#{t}" for t in result["hashtags"])
        self.save(update_fields=["caption_ia", "caption_style", "hashtags_ia"])
        AIGeneration.objects.create(
            post=self, user=self.auteur, type=AIGeneration.Type.LEGENDE,
            prompt=result.get("prompt", ""), result=result, moteur=result.get("engine", ""),
        )
        return result


class Reaction(models.Model):
    class Type(models.TextChoices):
        LIKE = "like", "👍"
        LOVE = "love", "❤️"
        HAHA = "haha", "😂"
        SAD = "sad", "😢"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reactions")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.LOVE)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "réaction"
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_reaction")]

    def __str__(self):
        return f"{self.user} {self.get_type_display()} {self.post_id}"

    @classmethod
    def toggle(cls, user, post, type=Type.LOVE):
        """Ajoute, change ou retire la réaction. Retourne la réaction active ou None."""
        existing = cls.objects.filter(user=user, post=post).first()
        if existing and existing.type == type:
            existing.delete()
            return None
        if existing:
            existing.type = type
            existing.save(update_fields=["type"])
            return existing
        return cls.objects.create(user=user, post=post, type=type)


class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    contenu = models.TextField(max_length=1000)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "commentaire"
        ordering = ["date"]

    def __str__(self):
        return f"{self.user}: {self.contenu[:40]}"


class AIGeneration(models.Model):
    """Historique de toutes les générations IA (traçabilité / dashboard admin)."""

    class Type(models.TextChoices):
        LEGENDE = "legende", "Légende + hashtags"
        TRANSCRIPTION = "transcription", "Transcription audio"
        IMAGE = "image", "Image IA"
        VISAGES = "visages", "Reconnaissance faciale"

    post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_generations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    type = models.CharField(max_length=20, choices=Type.choices)
    moteur = models.CharField(max_length=60, blank=True)
    prompt = models.TextField(blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "génération IA"
        verbose_name_plural = "générations IA"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} ({self.moteur}) #{self.pk}"
