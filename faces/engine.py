"""
Moteur de reconnaissance faciale (Gestion 4).

Utilise les modèles ONNX d'OpenCV Zoo :
- YuNet : détection de visages (boîtes englobantes + points clés)
- SFace : encodage facial (vecteur 128-d) et similarité cosinus

Les modèles (~40 Mo) sont téléchargés automatiquement au premier usage. Si
c'est impossible, on se rabat sur la détection Haar (sans identification) :
l'auteur peut alors taguer ses amis manuellement.
"""
import logging
import threading
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from PIL import Image, ImageOps

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

logger = logging.getLogger("blink.faces")

MODELS = {
    "yunet": (
        "face_detection_yunet_2023mar.onnx",
        200_000,
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ),
    "sface": (
        "face_recognition_sface_2021dec.onnx",
        30_000_000,
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ),
}

_lock = threading.Lock()
_download_failed = False


def model_path(key):
    filename, min_size, url = MODELS[key]
    path = Path(settings.FACE_MODELS_DIR) / filename
    return path, min_size, url


def ensure_models():
    """Télécharge les modèles si nécessaire. Retourne True s'ils sont disponibles."""
    global _download_failed
    if cv2 is None:
        return False
    with _lock:
        ok = True
        for key in MODELS:
            path, min_size, url = model_path(key)
            if path.exists() and path.stat().st_size >= min_size:
                continue
            if _download_failed:
                return False
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                logger.info("Téléchargement du modèle %s…", path.name)
                resp = requests.get(url, timeout=600)
                resp.raise_for_status()
                if len(resp.content) < min_size:
                    raise ValueError("fichier incomplet (pointeur Git LFS ?)")
                tmp = path.with_suffix(".part")
                tmp.write_bytes(resp.content)
                tmp.replace(path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Modèle %s indisponible : %s", path.name, exc)
                _download_failed = True
                ok = False
        return ok


def load_bgr(field_file, max_side=1024):
    """Charge une image Django en tableau BGR (orientation EXIF corrigée)."""
    field_file.open("rb")
    img = Image.open(field_file)
    img = ImageOps.exif_transpose(img).convert("RGB")
    field_file.close()
    img.thumbnail((max_side, max_side))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


class FaceEngine:
    def __init__(self):
        self.recognition = ensure_models()
        if self.recognition:
            self.detector = cv2.FaceDetectorYN.create(str(model_path("yunet")[0]), "", (320, 320), 0.7, 0.3, 5000)
            self.recognizer = cv2.FaceRecognizerSF.create(str(model_path("sface")[0]), "")
        else:
            # OpenCV 5 ne fournit plus CascadeClassifier : sans modèles, pas de détection.
            cascade_cls = getattr(cv2, "CascadeClassifier", None) if cv2 is not None else None
            data_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
            self.cascade = cascade_cls(data_dir + "haarcascade_frontalface_default.xml") if cascade_cls and data_dir else None

    @property
    def name(self):
        if self.recognition:
            return "opencv-yunet-sface"
        return "opencv-haar" if self.cascade is not None else "indisponible"

    def detect(self, bgr):
        """Retourne une liste de dicts {box: (x, y, w, h), score, encoding|None}."""
        h, w = bgr.shape[:2]
        faces = []
        if self.recognition:
            self.detector.setInputSize((w, h))
            _, found = self.detector.detect(bgr)
            for row in found if found is not None else []:
                aligned = self.recognizer.alignCrop(bgr, row)
                feature = self.recognizer.feature(aligned).flatten()
                x, y, fw, fh = (int(v) for v in row[:4])
                faces.append({"box": (x, y, fw, fh), "score": float(row[-1]), "encoding": feature.tolist()})
        elif self.cascade is not None:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            found = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40))
            for x, y, fw, fh in found:
                faces.append({"box": (int(x), int(y), int(fw), int(fh)), "score": 1.0, "encoding": None})
        return faces

    def similarity(self, enc_a, enc_b):
        a = np.asarray(enc_a, dtype=np.float32).reshape(1, -1)
        b = np.asarray(enc_b, dtype=np.float32).reshape(1, -1)
        return float(self.recognizer.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))


_engine = None


def get_engine():
    global _engine
    if _engine is None or (not _engine.recognition and not _download_failed):
        _engine = FaceEngine()
    return _engine
