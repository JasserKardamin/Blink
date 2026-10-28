from rest_framework import serializers

from accounts.models import User
from core.models import Report
from posts.models import Comment, Post


class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ["id", "post", "comment", "reported_user", "motif", "details", "date"]
        read_only_fields = ["id", "date"]

    def validate(self, attrs):
        user = self.context["request"].user
        post = attrs.get("post")
        comment = attrs.get("comment")
        reported_user = attrs.get("reported_user")

        # Must have exactly one target
        targets = [t for t in (post, comment, reported_user) if t is not None]
        if len(targets) != 1:
            raise serializers.ValidationError(
                "Vous devez spécifier exactement une cible : post, comment, ou reported_user."
            )

        # Cannot report own content
        if post and post.auteur == user:
            raise serializers.ValidationError("Vous ne pouvez pas signaler votre propre publication.")
        if comment and comment.user == user:
            raise serializers.ValidationError("Vous ne pouvez pas signaler votre propre commentaire.")
        if reported_user and reported_user == user:
            raise serializers.ValidationError("Vous ne pouvez pas vous signaler vous-même.")

        # Prevent duplicate pending reports
        existing = Report.objects.filter(
            auteur=user,
            statut=Report.Statut.EN_ATTENTE,
            post=post,
            comment=comment,
            reported_user=reported_user,
        ).exists()
        if existing:
            raise serializers.ValidationError("Vous avez déjà un signalement en attente pour ce contenu.")

        return attrs


class ReportResolveSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(choices=[Report.Statut.APPROUVE, Report.Statut.REJETE])
    action_prise = serializers.ChoiceField(
        choices=Report.Action.choices, default=Report.Action.AUCUNE, required=False
    )
    notes_moderation = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ReportSerializer(serializers.ModelSerializer):
    auteur_username = serializers.CharField(source="auteur.username", read_only=True)
    moderateur_username = serializers.CharField(source="moderateur.username", read_only=True, allow_null=True)
    motif_label = serializers.CharField(source="get_motif_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    action_prise_label = serializers.CharField(source="get_action_prise_display", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "auteur",
            "auteur_username",
            "post",
            "comment",
            "reported_user",
            "motif",
            "motif_label",
            "details",
            "statut",
            "statut_label",
            "action_prise",
            "action_prise_label",
            "moderateur",
            "moderateur_username",
            "notes_moderation",
            "date_traitement",
            "traite",
            "date",
        ]
        read_only_fields = fields
