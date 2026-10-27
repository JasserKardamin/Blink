from django.conf import settings

from .ai_clients import gemini_enabled, hf_enabled


def blink(request):
    ctx = {
        "AI_STATUS": {"gemini": gemini_enabled(), "hf": hf_enabled()},
        "DEBUG": settings.DEBUG,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_notifications"] = user.notifications.filter(lu=False).count()
        ctx["pending_friend_requests"] = user.friend_requests_received.filter(statut="en_attente").count()
    return ctx
