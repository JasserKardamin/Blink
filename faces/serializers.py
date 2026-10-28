from rest_framework import serializers

from accounts.models import User
from .models import DetectedFace, FaceEncoding, TagSuggestion


class UserFaceSummarySerializer(serializers.ModelSerializer):
    nom_complet = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "nom_complet", "photo_profil"]
        read_only_fields = fields


class FaceEncodingSerializer(serializers.ModelSerializer):
    user = UserFaceSummarySerializer(read_only=True)
    nb_dimensions = serializers.SerializerMethodField()

    class Meta:
        model = FaceEncoding
        fields = ["id", "user", "vecteur_encoding", "photo_reference", "date", "nb_dimensions"]
        read_only_fields = ["id", "user", "photo_reference", "date", "nb_dimensions"]

    def get_nb_dimensions(self, obj):
        return len(obj.vecteur_encoding or [])


class TagSuggestionSerializer(serializers.ModelSerializer):
    user_suggere = UserFaceSummarySerializer(read_only=True)
    user_suggere_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user_suggere", write_only=True, required=False
    )
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = TagSuggestion
        fields = [
            "id",
            "detected_face",
            "user_suggere",
            "user_suggere_id",
            "statut",
            "statut_label",
            "auto",
            "date",
        ]
        read_only_fields = ["id", "detected_face", "auto", "date", "statut_label"]


class TagStatusUpdateSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(
        choices=[TagSuggestion.Statut.ACCEPTE, TagSuggestion.Statut.REFUSE]
    )


class DetectedFaceSerializer(serializers.ModelSerializer):
    user_identifie = UserFaceSummarySerializer(read_only=True)
    user_identifie_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user_identifie", write_only=True, required=False, allow_null=True
    )
    tag_suggestions = TagSuggestionSerializer(many=True, read_only=True)
    bounding_box_coords = serializers.SerializerMethodField()

    class Meta:
        model = DetectedFace
        fields = [
            "id",
            "post",
            "image_source",
            "bounding_box",
            "bounding_box_coords",
            "encoding_detecte",
            "user_identifie",
            "user_identifie_id",
            "confiance",
            "confiance_pct",
            "date",
            "tag_suggestions",
        ]
        read_only_fields = [
            "id",
            "post",
            "image_source",
            "bounding_box_coords",
            "encoding_detecte",
            "confiance",
            "confiance_pct",
            "date",
            "tag_suggestions",
        ]

    def get_bounding_box_coords(self, obj):
        """
        Provides coordinates in [top, right, bottom, left] order if bounding box dict exists.
        """
        box = obj.bounding_box
        if not box:
            return None
        # box can be either {"top": ..., "right": ..., "bottom": ..., "left": ...}
        # or {"x": ..., "y": ..., "w": ..., "h": ...}
        if "top" in box and "right" in box and "bottom" in box and "left" in box:
            return [box["top"], box["right"], box["bottom"], box["left"]]
        if "x" in box and "y" in box and "w" in box and "h" in box:
            top = box["y"]
            left = box["x"]
            bottom = round(box["y"] + box["h"], 2)
            right = round(box["x"] + box["w"], 2)
            return [top, right, bottom, left]
        return box
