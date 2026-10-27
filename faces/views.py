from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, TemplateView

from accounts.models import User
from core.tasks import run_async
from posts.models import Post

from .engine import model_path
from .models import DetectedFace, FaceEncoding, TagSuggestion
from .services import confirm_tag, detect_faces_by_post_id, encode_user_by_id


class PostTagsView(LoginRequiredMixin, DetailView):
    """Écran « Tags des amis » : visages détectés, suggestions IA, validation."""

    template_name = "faces/post_tags.html"
    context_object_name = "post"

    def get_queryset(self):
        return Post.objects.filter(auteur=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        faces = list(self.object.detected_faces.select_related("user_identifie").prefetch_related(
            "tag_suggestions__user_suggere"
        ))
        for face in faces:
            accepted = [t for t in face.tag_suggestions.all() if t.statut == TagSuggestion.Statut.ACCEPTE]
            pending = [t for t in face.tag_suggestions.all() if t.statut == TagSuggestion.Statut.EN_ATTENTE]
            face.current = (accepted or pending or [None])[0]
        ctx["faces"] = faces
        ctx["detected"] = [f for f in faces if f.bounding_box]
        ctx["recognized"] = sum(1 for f in faces if f.current)
        ctx["friends"] = self.request.user.friends().order_by("username")
        ctx["engine_ready"] = model_path("sface")[0].exists()
        return ctx

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk, auteur=request.user)
        friends = {str(f.pk): f for f in request.user.friends()}
        confirmed = 0
        with transaction.atomic():
            for face in post.detected_faces.all():
                choice = request.POST.get(f"face_{face.pk}", "")
                if choice in friends:
                    confirm_tag(face, friends[choice])
                    confirmed += 1
                else:
                    face.tag_suggestions.all().delete()
                    if not face.bounding_box:
                        face.delete()  # tag manuel retiré
                        continue
                    face.user_identifie = None
                    face.save(update_fields=["user_identifie"])
            manual = request.POST.get("manual_friend", "")
            if manual in friends:
                face = DetectedFace.objects.create(post=post, bounding_box={}, confiance=1.0)
                confirm_tag(face, friends[manual])
                confirmed += 1
        messages.success(request, f"{confirmed} tag{'s' if confirmed > 1 else ''} confirmé{'s' if confirmed > 1 else ''}.")
        return redirect(post.get_absolute_url())


class RedetectView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk, auteur=request.user)
        run_async(detect_faces_by_post_id, post.pk)
        messages.info(request, "Analyse des visages relancée…")
        return redirect("faces:post_tags", pk=post.pk)


class MyTagsView(LoginRequiredMixin, TemplateView):
    """Photos où je suis identifié(e) + paramètres de confidentialité faciale."""

    template_name = "faces/my_tags.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["tags"] = TagSuggestion.objects.filter(
            user_suggere=user, statut=TagSuggestion.Statut.ACCEPTE
        ).select_related("detected_face__post__auteur")
        ctx["encoding"] = FaceEncoding.objects.filter(user=user).first()
        return ctx


class RemoveTagView(LoginRequiredMixin, View):
    """La personne identifiée (ou l'auteur) retire un tag."""

    def post(self, request, pk):
        tag = get_object_or_404(
            TagSuggestion.objects.select_related("detected_face__post"),
            Q(user_suggere=request.user) | Q(detected_face__post__auteur=request.user), pk=pk,
        )
        tag.statut = TagSuggestion.Statut.REFUSE
        tag.save(update_fields=["statut"])
        face = tag.detected_face
        face.user_identifie = None
        face.save(update_fields=["user_identifie"])
        messages.info(request, "Tag retiré.")
        return redirect(request.POST.get("next") or "faces:my_tags")


class FaceEncodingView(LoginRequiredMixin, View):
    """Recalcule ou supprime mon empreinte faciale (confidentialité)."""

    def post(self, request, action):
        user: User = request.user
        if action == "supprimer":
            FaceEncoding.objects.filter(user=user).delete()
            messages.info(request, "Ton empreinte faciale a été supprimée : tu ne seras plus reconnu(e) automatiquement.")
        elif user.photo_profil:
            run_async(encode_user_by_id, user.pk)
            messages.success(request, "Analyse de ta photo de profil en cours…")
        else:
            messages.info(request, "Ajoute une photo de profil où ton visage est bien visible.")
        return redirect("faces:my_tags")
