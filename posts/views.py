from datetime import timedelta
from itertools import chain

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from audio.models import AudioPost, Transcription
from audio.services import transcribe_by_id
from core.mixins import OwnerRequiredMixin, SuccessMessageDeleteMixin, json_or_redirect
from core.models import Notification, notify
from core.tasks import run_async
from faces.models import TagSuggestion
from faces.services import detect_faces_by_post_id

from .forms import CommentForm, PostForm, PostUpdateForm, ReportForm
from .models import AIGeneration, Comment, Post, Reaction


class VisiblePostMixin:
    def get_post(self):
        post = get_object_or_404(Post.objects.select_related("auteur"), pk=self.kwargs["pk"])
        if not post.can_view(self.request.user):
            raise Http404("Publication introuvable")
        return post


class ExploreView(ListView):
    """Publications publiques et visibles, des plus récentes aux plus anciennes."""

    template_name = "posts/explore.html"
    context_object_name = "posts"
    paginate_by = 24

    def get_queryset(self):
        return Post.objects.visible_to(self.request.user).with_stats()


class HashtagView(ListView):
    template_name = "posts/hashtag.html"
    context_object_name = "posts"
    paginate_by = 24

    def get_queryset(self):
        tag = self.kwargs["tag"]
        pattern = rf"#{tag}(\W|$)"
        return Post.objects.visible_to(self.request.user).filter(
            Q(caption__iregex=pattern) | Q(hashtags_ia__iregex=pattern)
        ).with_stats()

    def get_context_data(self, **kwargs):
        return super().get_context_data(tag=self.kwargs["tag"], **kwargs)


class PostDetailView(DetailView):
    template_name = "posts/post_detail.html"
    context_object_name = "post"

    def get_queryset(self):
        return Post.objects.visible_to(self.request.user).with_stats()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        post, user = self.object, self.request.user
        comments = post.comments.select_related("user__profile")
        audio_comments = post.audio_comments.select_related("user__profile", "transcription")
        for c in comments:
            c.kind = "texte"
        for c in audio_comments:
            c.kind = "vocal"
        ctx["thread"] = sorted(chain(comments, audio_comments), key=lambda c: c.date)
        ctx["comment_form"] = CommentForm()
        ctx["my_reaction"] = post.reaction_of(user)
        ctx["reaction_types"] = Reaction.Type.choices
        ctx["reaction_counts"] = {
            t: post.reactions.filter(type=t).count() for t, _ in Reaction.Type.choices
        }
        ctx["audio_posts"] = post.audio_posts.select_related("transcription")
        ctx["tagged_users"] = [
            t.user_suggere for t in TagSuggestion.objects.filter(
                detected_face__post=post, statut=TagSuggestion.Statut.ACCEPTE
            ).select_related("user_suggere")
        ]
        ctx["ai_versions"] = post.generated_images.filter(statut="termine")
        ctx["is_author"] = user == post.auteur
        if ctx["is_author"]:
            ctx["pending_tags"] = TagSuggestion.objects.filter(
                detected_face__post=post, statut=TagSuggestion.Statut.EN_ATTENTE
            ).count()
            # Analyse lancée à la publication : on ne l'attend que pendant les premières minutes.
            recent = post.date_creation > timezone.now() - timedelta(minutes=2)
            ctx["faces_analyzing"] = recent and not post.ai_generations.filter(type=AIGeneration.Type.VISAGES).exists()
        return ctx


class PostCreateView(LoginRequiredMixin, CreateView):
    form_class = PostForm
    template_name = "posts/post_form.html"

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.auteur = self.request.user
            post = form.save()
            audio = form.cleaned_data.get("audio")
            if audio:
                audio_post = AudioPost.objects.create(
                    user=self.request.user, post=post, fichier_audio=audio,
                    duree=form.cleaned_data.get("audio_duree") or 0,
                )
                Transcription.objects.create(audio_post=audio_post)
                run_async(transcribe_by_id, "post", audio_post.pk)
            run_async(detect_faces_by_post_id, post.pk)
        self.object = post
        messages.success(self.request, "C'est publié !", extra_tags=f"link:{post.get_absolute_url()}|Voir")
        return redirect(post.get_absolute_url())


class PostUpdateView(OwnerRequiredMixin, UpdateView):
    model = Post
    form_class = PostUpdateForm
    template_name = "posts/post_edit.html"
    owner_field = "auteur"
    allow_staff = False

    def form_valid(self, form):
        messages.success(self.request, "Publication modifiée.")
        return super().form_valid(form)


class PostDeleteView(OwnerRequiredMixin, SuccessMessageDeleteMixin, DeleteView):
    model = Post
    template_name = "posts/confirm_delete.html"
    owner_field = "auteur"
    success_url = reverse_lazy("core:home")
    success_message = "Publication supprimée."


class ReactView(LoginRequiredMixin, VisiblePostMixin, View):
    def post(self, request, pk):
        post = self.get_post()
        rtype = request.POST.get("type", Reaction.Type.LOVE)
        if rtype not in Reaction.Type.values:
            rtype = Reaction.Type.LOVE
        reaction = Reaction.toggle(request.user, post, rtype)
        if reaction:
            notify(post.auteur, Notification.Type.REACTION,
                   f"{request.user} a réagi {reaction.get_type_display()} à ta publication.",
                   acteur=request.user, lien=post.get_absolute_url())
        counts = dict(post.reactions.values("type").annotate(n=Count("id")).values_list("type", "n"))
        payload = {"active": bool(reaction), "type": reaction.type if reaction else None,
                   "count": post.get_likes(), "counts": counts}
        return json_or_redirect(request, payload, redirect(request.POST.get("next") or post.get_absolute_url()))


class CommentCreateView(LoginRequiredMixin, VisiblePostMixin, CreateView):
    form_class = CommentForm
    template_name = "posts/comment_form.html"

    def form_valid(self, form):
        post = self.get_post()
        form.instance.user = self.request.user
        form.instance.post = post
        comment = form.save()
        notify(post.auteur, Notification.Type.COMMENTAIRE,
               f"{self.request.user} a commenté : « {comment.contenu[:80]} »",
               acteur=self.request.user, lien=post.get_absolute_url())
        return redirect(f"{post.get_absolute_url()}#commentaires")


class CommentUpdateView(OwnerRequiredMixin, UpdateView):
    model = Comment
    form_class = CommentForm
    template_name = "posts/comment_form.html"
    allow_staff = False

    def get_success_url(self):
        return f"{self.object.post.get_absolute_url()}#commentaires"


class CommentDeleteView(LoginRequiredMixin, DeleteView):
    model = Comment
    template_name = "posts/confirm_delete.html"

    def get_queryset(self):
        # L'auteur du commentaire ou l'auteur de la publication peuvent supprimer.
        user = self.request.user
        return Comment.objects.filter(Q(user=user) | Q(post__auteur=user))

    def get_success_url(self):
        return f"{self.object.post.get_absolute_url()}#commentaires"


class ReportCreateView(LoginRequiredMixin, VisiblePostMixin, CreateView):
    form_class = ReportForm
    template_name = "posts/report_form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(post=self.get_post(), **kwargs)

    def form_valid(self, form):
        post = self.get_post()
        form.instance.auteur = self.request.user
        form.instance.post = post
        try:
            with transaction.atomic():
                form.save()
            messages.success(self.request, "Merci, la modération va examiner cette publication.")
        except IntegrityError:
            messages.info(self.request, "Tu as déjà signalé cette publication.")
        return redirect(post.get_absolute_url())
