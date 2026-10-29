"""
Double authentification par TOTP (Google Authenticator, Authy, 2FAS…).

Le secret est généré à l'activation et confirmé par un premier code ; des codes
de secours à usage unique (stockés hachés) permettent de se connecter sans téléphone.
"""
import hashlib
import hmac
import secrets
import time

import pyotp
import segno
from django.conf import settings

RECOVERY_CODE_COUNT = 10
SESSION_PENDING_USER = "2fa_pending_user"
SESSION_PENDING_BACKEND = "2fa_pending_backend"
SESSION_PENDING_NEXT = "2fa_pending_next"
SESSION_PENDING_SINCE = "2fa_pending_since"
SESSION_ATTEMPTS = "2fa_attempts"
SESSION_SETUP_SECRET = "2fa_setup_secret"


def new_secret():
    return pyotp.random_base32()


def provisioning_uri(user, secret):
    return pyotp.TOTP(secret).provisioning_uri(name=user.email or user.username, issuer_name=settings.TWO_FACTOR_ISSUER)


def qr_code_svg(uri):
    """QR code SVG à insérer directement dans la page (aucun fichier, aucun service externe)."""
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#13112A", light="#FFFFFF")


def normalize(code):
    return "".join(str(code or "").split()).replace("-", "").lower()


def match_totp(secret, code, last_step=0):
    """Retourne le pas de temps du code s'il est valide (±30 s) et pas déjà utilisé, sinon None."""
    code = normalize(code)
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    now = time.time()
    for drift in (-1, 0, 1):
        for_time = int(now + drift * totp.interval)
        step = for_time // totp.interval
        if step > last_step and hmac.compare_digest(totp.at(for_time), code):
            return step
    return None


def hash_recovery_code(code):
    return hashlib.sha256(normalize(code).encode()).hexdigest()


def generate_recovery_codes():
    """Retourne (codes en clair à montrer une seule fois, empreintes à stocker)."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(5)
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [hash_recovery_code(c) for c in codes]
