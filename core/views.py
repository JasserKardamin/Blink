from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from accounts.models import User
from posts.models import Post

from .models import Notification


class HomeView(ListView):
    """Fil d'actualité (connecté) ou page d'accueil publique (visiteur)."""

    context_object_name = "posts"
    paginate_by = 10

    def get_template_names(self):
        return ["core/feed.html" if self.request.user.is_authenticated else "core/landing.html"]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return Post.objects.feed_for(user).with_stats(user)
        return Post.objects.visible_to(user).with_stats()[:9]

    def get_paginate_by(self, queryset):
        return self.paginate_by if self.request.user.is_authenticated else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            known = user.friend_ids() | set(user.following.values_list("pk", flat=True)) | {user.pk}
            ctx["suggestions"] = User.objects.filter(is_active=True).exclude(pk__in=known).order_by("-date_joined")[:5]
        return ctx


class SearchView(TemplateView):
    template_name = "core/search.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        ctx["q"] = q
        if q:
            term = q.lstrip("#@")
            ctx["users"] = User.objects.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term),
                is_active=True,
            ).select_related("profile")[:12]
            ctx["posts"] = Post.objects.visible_to(self.request.user).filter(
                Q(caption__icontains=term) | Q(hashtags_ia__icontains=term) | Q(caption_ia__icontains=term)
            ).with_stats()[:30]
        else:
            ctx["trending"] = trending_hashtags(self.request.user)
            ctx["posts"] = Post.objects.visible_to(self.request.user).with_stats()[:30]
        return ctx


def trending_hashtags(user, limit=12):
    counts = {}
    for post in Post.objects.visible_to(user).only("caption", "hashtags_ia")[:300]:
        for tag in post.get_hashtags():
            counts[tag.lower()] = counts.get(tag.lower(), 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "core/notifications.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(destinataire=self.request.user).select_related("acteur__profile")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # On fige la liste affichée avant de tout marquer comme lu.
        ctx["unread_ids"] = set(
            Notification.objects.filter(destinataire=self.request.user, lu=False).values_list("pk", flat=True)
        )
        Notification.objects.filter(destinataire=self.request.user, lu=False).update(lu=True)
        return ctx


class NotificationOpenView(LoginRequiredMixin, View):
    def get(self, request, pk):
        notif = get_object_or_404(Notification, pk=pk, destinataire=request.user)
        notif.lu = True
        notif.save(update_fields=["lu"])
        return redirect(notif.lien or "core:notifications")


from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import UpdateView, DeleteView
from django.urls import reverse_lazy
from .models import Report
from posts.forms import ReportForm

class UserReportListView(LoginRequiredMixin, ListView):
    template_name = 'core/report_list.html'
    context_object_name = 'reports'
    paginate_by = 20

    def get_queryset(self):
        return Report.objects.filter(auteur=self.request.user).select_related(
            'post', 'comment', 'reported_user', 'moderateur'
        ).order_by('-date')


class UserReportUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Report
    form_class = ReportForm
    template_name = 'core/report_form.html'
    success_url = reverse_lazy('core:my_reports')

    def test_func(self):
        report = self.get_object()
        return report.auteur == self.request.user and report.statut == Report.Statut.EN_ATTENTE

    def form_valid(self, form):
        messages.success(self.request, 'Signalement mis à jour avec succès.')
        return super().form_valid(form)


class UserReportDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Report
    template_name = 'core/report_confirm_delete.html'
    success_url = reverse_lazy('core:my_reports')

    def test_func(self):
        report = self.get_object()
        return report.auteur == self.request.user and report.statut == Report.Statut.EN_ATTENTE

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Votre signalement a été retiré.')
        return super().delete(request, *args, **kwargs)
