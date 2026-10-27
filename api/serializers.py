from rest_framework import serializers

from accounts.models import Friendship, User
from aistudio.models import AIPromptTemplate, GeneratedImage, ImageFilter
from audio.models import AudioComment, AudioPost, Transcription
from core.models import Notification
from faces.models import DetectedFace, TagSuggestion
from posts.models import Comment, Post, Reaction


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source="display_avatar_url", read_only=True)
    ville = serializers.CharField(source="profile.ville", read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "bio", "avatar", "ville", "date_joined")
        read_only_fields = fields


class TranscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcription
        fields = ("id", "texte", "langue", "statut", "moteur", "erreur", "date")
        read_only_fields = ("statut", "moteur", "erreur", "date")


class AudioPostSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    transcription = TranscriptionSerializer(read_only=True)

    class Meta:
        model = AudioPost
        fields = ("id", "user", "post", "fichier_audio", "description", "duree", "transcription", "date")
        read_only_fields = ("date",)


class AudioCommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    transcription = TranscriptionSerializer(read_only=True)

    class Meta:
        model = AudioComment
        fields = ("id", "user", "post", "fichier_audio", "duree", "transcription", "date")
        read_only_fields = ("date",)


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "user", "post", "contenu", "date")
        read_only_fields = ("post", "date")


class PostSerializer(serializers.ModelSerializer):
    auteur = UserSerializer(read_only=True)
    hashtags = serializers.ListField(source="get_hashtags", read_only=True)
    nb_reactions = serializers.IntegerField(read_only=True, required=False)
    nb_commentaires = serializers.IntegerField(read_only=True, required=False)
    ma_reaction = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = (
            "id", "auteur", "image", "caption", "caption_ia", "caption_style", "hashtags_ia", "hashtags",
            "visibilite", "nb_reactions", "nb_commentaires", "ma_reaction", "tags", "date_creation",
            "date_modification",
        )
        read_only_fields = ("date_creation", "date_modification")

    def get_ma_reaction(self, obj):
        request = self.context.get("request")
        reaction = obj.reaction_of(request.user) if request else None
        return reaction.type if reaction else None

    def get_tags(self, obj):
        return list(
            TagSuggestion.objects.filter(detected_face__post=obj, statut=TagSuggestion.Statut.ACCEPTE)
            .values_list("user_suggere__username", flat=True)
        )


class PostUpdateSerializer(PostSerializer):
    class Meta(PostSerializer.Meta):
        read_only_fields = PostSerializer.Meta.read_only_fields + ("image",)


class ReactionSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Reaction.Type.choices, default=Reaction.Type.LOVE)


class CaptionRequestSerializer(serializers.Serializer):
    image = serializers.ImageField(required=False)
    post_id = serializers.IntegerField(required=False)
    style = serializers.ChoiceField(choices=Post.Style.choices, default=Post.Style.POETIQUE)
    context = serializers.CharField(required=False, allow_blank=True, max_length=500)
    template_id = serializers.IntegerField(required=False)

    def validate(self, data):
        if not data.get("image") and not data.get("post_id"):
            raise serializers.ValidationError("Fournir une image ou un post_id.")
        return data


class FriendshipSerializer(serializers.ModelSerializer):
    user_from = UserSerializer(read_only=True)
    user_to = UserSerializer(read_only=True)

    class Meta:
        model = Friendship
        fields = ("id", "user_from", "user_to", "statut", "date")


class NotificationSerializer(serializers.ModelSerializer):
    acteur = UserSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "type", "message", "lien", "lu", "acteur", "date")
        read_only_fields = ("type", "message", "lien", "acteur", "date")


class GeneratedImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedImage
        fields = ("id", "post", "type", "style", "filtre", "template", "image_originale", "image_generee",
                  "prompt", "modele", "statut", "erreur", "date")
        read_only_fields = ("image_originale", "image_generee", "prompt", "modele", "statut", "erreur", "date")


class ImageFilterSerializer(serializers.ModelSerializer):
    systeme = serializers.BooleanField(source="is_system", read_only=True)

    class Meta:
        model = ImageFilter
        fields = ("id", "nom", "description", "parametres", "preview", "systeme", "date")


class AIPromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIPromptTemplate
        fields = ("id", "nom", "template_prompt", "type", "date")


class TagSuggestionSerializer(serializers.ModelSerializer):
    user_suggere = UserSerializer(read_only=True)

    class Meta:
        model = TagSuggestion
        fields = ("id", "user_suggere", "statut", "auto", "date")


class DetectedFaceSerializer(serializers.ModelSerializer):
    user_identifie = UserSerializer(read_only=True)
    tag_suggestions = TagSuggestionSerializer(many=True, read_only=True)

    class Meta:
        model = DetectedFace
        fields = ("id", "post", "image_source", "bounding_box", "user_identifie", "confiance", "tag_suggestions", "date")
