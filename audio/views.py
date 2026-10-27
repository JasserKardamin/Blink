from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import OwnerRequiredMixin, SuccessMessageDeleteMixin, json_or_redirect
from core.models import Notification, notify
from core.tasks import run_async
from posts.models import Post

from .forms import AudioCommentForm, AudioPostForm, TranscriptionForm
from .models import AudioComment, AudioPost, Transcription
from .services import transcribe_by_id


def visible_audio_posts(user):
    """Vocaux autonomes visibles + vocaux attachés à des posts visibles."""
    posts = Post.objects.visible_to(user)
    return AudioPost.objects.filter(Q(post__isnull=True) | Q(post__in=posts)).select_related(
        "user__profile", "transcription", "post"
    )


class AudioPostListView(LoginRequiredMixin, ListView):
    template_name = "audio/audio_list.html"
    context_object_name = "audio_posts"
    paginate_by = 20

    def get_queryset(self):
        qs = visible_audio_posts(self.request.user)
        if self.request.GET.get("filtre") == "moi":
            qs = qs.filter(user=self.request.user)
        return qs


class AudioPostCreateView(LoginRequiredMixin, CreateView):
    form_class = AudioPostForm
    template_name = "audio/audio_form.html"

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.user = self.request.user
            audio_post = form.save()
            Transcription.objects.create(audio_post=audio_post)
            run_async(transcribe_by_id, "post", audio_post.pk)
        messages.success(self.request, "Vocal publié ! La transcription arrive dans quelques secondes.")
        return redirect(audio_post.get_absolute_url())


class AudioPostDetailView(LoginRequiredMixin, DetailView):
    template_name = "audio/audio_detail.html"
    context_object_name = "audio_post"

    def get_queryset(self):
        return visible_audio_posts(self.request.user)


class AudioPostDeleteView(OwnerRequiredMixin, SuccessMessageDeleteMixin, DeleteView):
    model = AudioPost
    template_name = "posts/confirm_delete.html"
    success_url = reverse_lazy("audio:list")
    success_message = "Vocal supprimé."

    def form_valid(self, form):
        self.object.fichier_audio.delete(save=False)
        return super().form_valid(form)


class TranscriptionUpdateView(LoginRequiredMixin, UpdateView):
    model = Transcription
    form_class = TranscriptionForm
    template_name = "audio/transcription_form.html"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.owner != self.request.user:
            raise PermissionDenied
        return obj

    def form_valid(self, form):
        form.instance.statut = Transcription.Statut.TERMINE
        form.instance.moteur = "manuel"
        form.instance.erreur = ""
        messages.success(self.request, "Transcription mise à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        if self.object.audio_post_id:
            ap = self.object.audio_post
            return ap.post.get_absolute_url() if ap.post_id else ap.get_absolute_url()
        return f"{self.object.audio_comment.post.get_absolute_url()}#commentaires"


class RetranscribeView(LoginRequiredMixin, View):
    """Relance la transcription IA d'un vocal (post ou commentaire)."""

    def post(self, request, kind, pk):
        model = AudioPost if kind == "post" else AudioComment
        obj = get_object_or_404(model, pk=pk)
        if obj.user != request.user:
            raise PermissionDenied
        transcription = getattr(obj, "transcription", None)
        if transcription is None:
            transcription = Transcription.objects.create(audio_post=obj if kind == "post" else None)
            if kind != "post":
                obj.transcription = transcription
                obj.save(update_fields=["transcription"])
        transcription.statut = Transcription.Statut.EN_ATTENTE
        transcription.save(update_fields=["statut"])
        run_async(transcribe_by_id, kind, obj.pk)
        payload = {"transcription": transcription.pk, "statut": transcription.statut}
        return json_or_redirect(request, payload, redirect(request.POST.get("next") or "audio:list"))


class AudioCommentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        if not post.can_view(request.user):
            raise Http404
        form = AudioCommentForm(request.POST, request.FILES)
        if not form.is_valid():
            errors = "; ".join(e for errs in form.errors.values() for e in errs)
            messages.error(request, f"On n'a pas pu lire ton message vocal. {errors}", extra_tags="retry")
            return json_or_redirect(request, {"errors": form.errors}, redirect(post.get_absolute_url()), status=400)
        with transaction.atomic():
            comment = form.save(commit=False)
            comment.user, comment.post = request.user, post
            comment.transcription = Transcription.objects.create()
            comment.save()
            run_async(transcribe_by_id, "comment", comment.pk)
        notify(post.auteur, Notification.Type.COMMENTAIRE_VOCAL, f"{request.user} a laissé un commentaire vocal.",
               acteur=request.user, lien=post.get_absolute_url())
        payload = {"id": comment.pk, "transcription": comment.transcription_id}
        return json_or_redirect(request, payload, redirect(f"{post.get_absolute_url()}#commentaires"), status=201)


class AudioCommentDeleteView(LoginRequiredMixin, DeleteView):
    model = AudioComment
    template_name = "posts/confirm_delete.html"

    def get_queryset(self):
        user = self.request.user
        return AudioComment.objects.filter(Q(user=user) | Q(post__auteur=user))

    def form_valid(self, form):
        self.object.fichier_audio.delete(save=False)
        if self.object.transcription_id:
            self.object.transcription.delete()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("posts:detail", kwargs={"pk": self.object.post_id}) + "#commentaires"
