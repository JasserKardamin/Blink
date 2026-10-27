from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restreint une vue de détail/modification au propriétaire de l'objet (ou au staff)."""

    owner_field = "user"
    allow_staff = True

    def get_owner(self, obj):
        owner = obj
        for part in self.owner_field.split("."):
            owner = getattr(owner, part)
        return owner

    def test_func(self):
        user = self.request.user
        if self.allow_staff and user.is_staff:
            return True
        return self.get_owner(self.get_object()) == user


class SuccessMessageDeleteMixin:
    success_message = ""

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response


def wants_json(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get(
        "accept", ""
    )


def json_or_redirect(request, payload, redirect_response, status=200):
    if wants_json(request):
        return JsonResponse(payload, status=status)
    return redirect_response
