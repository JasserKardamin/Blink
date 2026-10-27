"""
Filtres artistiques locaux (OpenCV + Pillow).

Ils servent de filtres « instantanés » et de solution de repli quand Stable
Diffusion (Hugging Face) n'est pas disponible.
"""
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import cv2
except ImportError:  # pragma: no cover - OpenCV est une dépendance du projet
    cv2 = None


def _to_cv(img):
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _to_pil(arr):
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


def anime(img):
    if cv2 is None:
        return ImageOps.posterize(img.filter(ImageFilter.ModeFilter(5)), 3)
    bgr = _to_cv(img)
    smooth = bgr
    for _ in range(2):
        smooth = cv2.bilateralFilter(smooth, 9, 60, 60)
    # Quantification des couleurs (aplats façon dessin animé)
    data = np.float32(smooth).reshape(-1, 3)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(data, 10, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    quant = np.uint8(centers)[labels.flatten()].reshape(smooth.shape)
    gray = cv2.medianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 7)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 4)
    out = cv2.bitwise_and(quant, quant, mask=edges)
    return ImageEnhance.Color(_to_pil(out)).enhance(1.35)


def peinture(img):
    if cv2 is None:
        return img.filter(ImageFilter.ModeFilter(7)).filter(ImageFilter.SMOOTH_MORE)
    out = cv2.stylization(_to_cv(img), sigma_s=60, sigma_r=0.45)
    pil = _to_pil(out).filter(ImageFilter.ModeFilter(3))
    return ImageEnhance.Color(pil).enhance(1.25)


def cyberpunk(img):
    rgb = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    lum = rgb.mean(axis=2, keepdims=True)
    shadows = np.array([0.15, 0.05, 0.45])  # violet
    highlights = np.array([1.0, 0.25, 0.75])  # magenta
    mids = np.array([0.1, 0.9, 1.0])  # cyan
    graded = np.where(lum < 0.5, shadows + (mids - shadows) * (lum * 2), mids + (highlights - mids) * ((lum - 0.5) * 2))
    mixed = np.clip(rgb * 0.45 + graded * 0.75, 0, 1)
    out = Image.fromarray((mixed * 255).astype(np.uint8))
    glow = out.filter(ImageFilter.GaussianBlur(radius=max(2, img.width // 150)))
    out = Image.blend(out, glow, 0.35)
    return ImageEnhance.Contrast(out).enhance(1.25)


def aquarelle(img):
    if cv2 is None:
        return img.filter(ImageFilter.ModeFilter(9)).filter(ImageFilter.GaussianBlur(1))
    bgr = cv2.edgePreservingFilter(_to_cv(img), flags=1, sigma_s=60, sigma_r=0.4)
    bgr = cv2.stylization(bgr, sigma_s=30, sigma_r=0.6)
    pil = _to_pil(bgr)
    paper = Image.new("RGB", pil.size, (250, 246, 238))
    pil = Image.blend(pil, paper, 0.18)
    return ImageEnhance.Brightness(pil).enhance(1.05)


def croquis(img):
    if cv2 is None:
        gray = ImageOps.grayscale(img)
        return ImageOps.autocontrast(gray.filter(ImageFilter.CONTOUR)).convert("RGB")
    gray, _ = cv2.pencilSketch(_to_cv(img), sigma_s=50, sigma_r=0.08, shade_factor=0.04)
    return Image.fromarray(gray).convert("RGB")


def vintage(img):
    gray = ImageOps.grayscale(img)
    sepia = ImageOps.colorize(gray, black=(45, 30, 20), white=(255, 236, 200))
    sepia = Image.blend(img.convert("RGB"), sepia, 0.75)
    w, h = sepia.size
    yy, xx = np.ogrid[:h, :w]
    dist = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    vignette = np.clip(1.15 - 0.55 * dist, 0.35, 1.0)[..., None]
    arr = (np.asarray(sepia).astype(np.float32) * vignette).astype(np.uint8)
    noise = np.random.default_rng(0).normal(0, 8, arr.shape)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


FILTERS = {
    "anime": anime,
    "peinture": peinture,
    "cyberpunk": cyberpunk,
    "aquarelle": aquarelle,
    "croquis": croquis,
    "vintage": vintage,
}


def apply_filter(img, style, parametres=None, max_side=1280):
    """Applique un style local à une image PIL et renvoie une nouvelle image."""
    params = parametres or {}
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    styled = FILTERS.get(style, anime)(img)
    if styled.size != img.size:
        styled = styled.resize(img.size)
    intensite = float(params.get("intensite", 1.0))
    if intensite < 1.0:
        styled = Image.blend(img, styled.convert("RGB"), max(0.0, intensite))
    if "saturation" in params:
        styled = ImageEnhance.Color(styled).enhance(float(params["saturation"]))
    if "contraste" in params:
        styled = ImageEnhance.Contrast(styled).enhance(float(params["contraste"]))
    if "luminosite" in params:
        styled = ImageEnhance.Brightness(styled).enhance(float(params["luminosite"]))
    return styled.convert("RGB")
