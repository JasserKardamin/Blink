from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from core.models import Notification, notify
from core.tasks import run_async
from faces.services import encode_user_by_id

from .forms import LoginForm, ProfileForm, SignUpForm, UserUpdateForm
from .models import Friendship, User


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("accounts:edit")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend="accounts.backends.EmailOrUsernameBackend")
        messages.success(self.request, "Bienvenue sur Blink ! Ajoute une photo de profil pour être reconnu(e) par tes amis.")
        return response


class BlinkLoginView(LoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class ProfileDetailView(DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"
    context_object_name = "profile_user"
    template_name = "accounts/profile.html"

    def get_queryset(self):
        return User.objects.filter(is_active=True).select_related("profile")

    def get_context_data(self, **kwargs):
        from posts.models import Post

        ctx = super().get_context_data(**kwargs)
        user, viewer = self.object, self.request.user
        ctx["posts"] = Post.objects.visible_to(viewer).filter(auteur=user).with_stats()
        ctx["friends_count"] = user.friends().count()
        ctx["followers_count"] = user.followers.count()
        ctx["following_count"] = user.following.count()
        ctx["audio_posts"] = user.audio_posts.filter(post__isnull=True).select_related("transcription")[:6]
        if viewer.is_authenticated and viewer != user:
            ctx["friendship"] = viewer.friendship_with(user)
            ctx["is_following"] = viewer.is_following(user)
        return ctx


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    form_class = UserUpdateForm
    template_name = "accounts/profile_edit.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("profile_form", ProfileForm(instance=self.request.user.profile))
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        profile_form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                form.save()
                profile_form.save()
                if "photo_profil" in form.changed_data:
                    run_async(encode_user_by_id, self.object.pk)
            messages.success(request, "Profil mis à jour.")
            return redirect(self.object.get_absolute_url())
        return self.render_to_response(self.get_context_data(form=form, profile_form=profile_form))


class FriendsView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/friends.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        me = self.request.user
        friends = me.friends().select_related("profile")
        pending = Friendship.objects.filter(statut=Friendship.Statut.EN_ATTENTE)
        related_ids = Friendship.objects.filter(Q(user_from=me) | Q(user_to=me)).values_list("user_from", "user_to")
        excluded = {me.pk} | {pk for pair in related_ids for pk in pair}
        ctx.update(
            friends=friends,
            received=pending.filter(user_to=me).select_related("user_from__profile"),
            sent=pending.filter(user_from=me).select_related("user_to__profile"),
            suggestions=User.objects.filter(is_active=True).exclude(pk__in=excluded).order_by("-date_joined")[:8],
        )
        return ctx


class FriendRequestView(LoginRequiredMixin, View):
    """Envoie une demande d'ami (ou accepte celle reçue en sens inverse)."""

    def post(self, request, username):
        target = get_object_or_404(User, username=username, is_active=True)
        me = request.user
        if target == me:
            return redirect(target.get_absolute_url())
        existing = me.friendship_with(target)
        if existing is None:
            Friendship.objects.create(user_from=me, user_to=target)
            notify(target, Notification.Type.DEMANDE_AMI, f"{me} t'a envoyé une demande d'ami.",
                   acteur=me, lien=reverse("accounts:friends"))
            messages.success(request, f"Demande envoyée à {target}.")
        elif existing.user_to == me and existing.statut != Friendship.Statut.ACCEPTE:
            _accept(existing)
            messages.success(request, f"Tu es maintenant ami(e) avec {target}.")
        elif existing.user_from == me and existing.statut == Friendship.Statut.REFUSE:
            existing.statut = Friendship.Statut.EN_ATTENTE
            existing.save(update_fields=["statut"])
            messages.info(request, "Demande renvoyée.")
        return redirect(request.POST.get("next") or target.get_absolute_url())


def _accept(friendship):
    friendship.statut = Friendship.Statut.ACCEPTE
    friendship.save(update_fields=["statut"])
    friendship.user_to.follow(friendship.user_from)
    friendship.user_from.follow(friendship.user_to)
    notify(friendship.user_from, Notification.Type.AMI_ACCEPTE,
           f"{friendship.user_to} a accepté ta demande d'ami.",
           acteur=friendship.user_to, lien=friendship.user_to.get_absolute_url())


class FriendRespondView(LoginRequiredMixin, View):
    def post(self, request, pk, action):
        friendship = get_object_or_404(Friendship, pk=pk, user_to=request.user)
        if action == "accepter":
            _accept(friendship)
            messages.success(request, f"{friendship.user_from} fait maintenant partie de tes amis.")
        elif action == "refuser":
            friendship.statut = Friendship.Statut.REFUSE
            friendship.save(update_fields=["statut"])
            messages.info(request, "Demande refusée.")
        return redirect(request.POST.get("next") or "accounts:friends")


class FriendRemoveView(LoginRequiredMixin, View):
    """Retire un ami ou annule une demande envoyée."""

    def post(self, request, username):
        target = get_object_or_404(User, username=username)
        friendship = request.user.friendship_with(target)
        if friendship and (friendship.statut == Friendship.Statut.ACCEPTE or friendship.user_from == request.user):
            friendship.delete()
            messages.info(request, f"{target} a été retiré(e).")
        return redirect(request.POST.get("next") or "accounts:friends")


class FollowToggleView(LoginRequiredMixin, View):
    def post(self, request, username):
        target = get_object_or_404(User, username=username, is_active=True)
        if request.user.is_following(target):
            request.user.unfollow(target)
        elif target != request.user:
            request.user.follow(target)
            notify(target, Notification.Type.ABONNEMENT, f"{request.user} s'est abonné(e) à toi.",
                   acteur=request.user, lien=request.user.get_absolute_url())
        return redirect(request.POST.get("next") or target.get_absolute_url())
