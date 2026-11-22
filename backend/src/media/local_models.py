"""Open-source models that run on this machine (no API calls): CLIP for pictures and PANNs for sounds.

  Clip         - OpenCLIP ViT-B-32 (LAION). Scores a frame against short descriptions of action and of dull
                 screens, and fingerprints it so repeated scenes can be told from new ones.
  AudioTagger  - PANNs Cnn14 (AudioSet, 527 sound classes). Hears sirens, gunfire, explosions, screaming,
                 crashes and laughter even when chat and the streamer are quiet.

Ported from the GTA clipper with general prompts. Heavy imports (torch, open_clip, panns_inference) stay inside
functions so the backend starts without them; install them with the ``frame-scan`` dependency group.
Weights are fetched once by ``python -m src.media.local_models``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

MODELS = Path(os.environ.get("FRAME_SCAN_MODELS_DIR") or "/app/models")
PANNS_CKPT = MODELS / "Cnn14_mAP=0.431.pth"
PANNS_LABELS = Path.home() / "panns_data" / "class_labels_indices.csv"
CLIP_ARCH, CLIP_TAG = "ViT-B-32", "laion2b_s34b_b79k"

CKPT_URL = "https://zenodo.org/records/3987831/files/Cnn14_mAP%3D0.431.pth?download=1"
LABEL_URL = "https://raw.githubusercontent.com/qiuqiangkong/audioset_tagging_cnn/master/metadata/class_labels_indices.csv"


def device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


# Descriptions CLIP compares each frame with: moments worth clipping, dull screens, and content to avoid.
ACTION = [
    "a car chase", "police cars with sirens chasing a car", "a helicopter flying low over a city",
    "a car crash", "a car flipping through the air", "a huge explosion with fire", "a burning vehicle",
    "a shootout with guns", "a character shooting a gun", "a fist fight", "a wild animal attacking",
    "a shark in the ocean", "a big monster creature", "a speedboat racing on water", "an airplane flying",
    "a plane crash", "a skydiver with a parachute", "a motorcycle stunt jump", "a sports car racing at high speed",
    "a character falling from a great height", "a crowd of people running in panic", "a tornado or storm",
    "a strange creature never seen before", "a boss fight",
]
BORING = [
    "a video game pause menu", "a video game map screen", "a loading screen", "a black screen",
    "an inventory or shop menu", "a phone screen", "a settings menu with text",
    "a character standing still in a room", "a character walking slowly down a street",
    "a person talking to a webcam", "a character sitting in a parked car", "a dialogue scene with two people talking",
    "a cinematic cutscene with black bars", "a stream starting soon screen", "a chat overlay with only text",
]
UNSAFE = [
    "a shirtless man in underwear", "a woman in underwear", "a strip club with dancers", "nudity",
    "a sexual scene", "blood and gore",
]

# AudioSet label -> weight: how much it means "something is happening".
SOUNDS = {
    "Siren": 1.0, "Police car (siren)": 1.0, "Emergency vehicle": 0.9, "Civil defense siren": 0.6,
    "Gunshot, gunfire": 1.0, "Machine gun": 1.0, "Fusillade": 1.0, "Artillery fire": 0.8, "Cap gun": 0.6,
    "Explosion": 1.0, "Boom": 0.8, "Burst, pop": 0.4, "Fire": 0.5,
    "Helicopter": 0.9, "Aircraft": 0.6, "Fixed-wing aircraft, airplane": 0.6, "Jet engine": 0.6,
    "Skidding": 0.8, "Tire squeal": 0.8, "Car alarm": 0.6, "Vehicle horn, car horn, honking": 0.4,
    "Smash, crash": 0.9, "Breaking": 0.6, "Glass": 0.4, "Shatter": 0.7,
    "Screaming": 0.9, "Yell": 0.6, "Shout": 0.5, "Laughter": 0.5, "Belly laugh": 0.7,
    "Motorboat, speedboat": 0.6, "Roar": 0.6, "Growling": 0.6, "Dog": 0.3, "Bark": 0.3,
}


def models_ready() -> bool:
    """True when the libraries are installed and the weights are on disk."""
    try:
        import open_clip  # noqa: F401
        import panns_inference.models  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return any((MODELS / "clip").glob("**/open_clip_model*")) and PANNS_CKPT.exists()


class Clip:
    def __init__(self) -> None:
        import open_clip
        import torch

        self.torch = torch
        self.dev = device()
        self.model, _, self.prep = open_clip.create_model_and_transforms(
            CLIP_ARCH, pretrained=CLIP_TAG, cache_dir=str(MODELS / "clip"))
        self.model = self.model.to(self.dev).eval()
        if self.dev == "cuda":
            self.model = self.model.half()
        tokenizer = open_clip.get_tokenizer(CLIP_ARCH)
        self.prompts = ACTION + BORING + UNSAFE
        self.n_action, self.n_boring = len(ACTION), len(BORING)
        with torch.no_grad():
            text = self.model.encode_text(tokenizer(self.prompts).to(self.dev))
            self.text = (text / text.norm(dim=-1, keepdim=True)).float().cpu().numpy()

    def embed(self, paths: List[str], batch: int = 32) -> np.ndarray:
        from PIL import Image

        out = []
        with self.torch.no_grad():
            for start in range(0, len(paths), batch):
                images = self.torch.stack([self.prep(Image.open(p).convert("RGB")) for p in paths[start:start + batch]])
                images = images.to(self.dev)
                if self.dev == "cuda":
                    images = images.half()
                encoded = self.model.encode_image(images)
                out.append((encoded / encoded.norm(dim=-1, keepdim=True)).float().cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 512), np.float32)

    def score(self, embeddings: np.ndarray) -> List[Dict[str, Any]]:
        """Per frame: how action-like, dull and unsafe it looks, and the closest description."""
        logits = 100.0 * embeddings @ self.text.T
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=1, keepdims=True)
        a, b = self.n_action, self.n_action + self.n_boring
        rows = []
        for row in probs:
            best = int(row.argmax())
            rows.append({
                "action": float(row[:a].sum()), "boring": float(row[a:b].sum()), "unsafe": float(row[b:].sum()),
                "best": self.prompts[best], "best_kind": "action" if best < a else "boring" if best < b else "unsafe",
            })
        return rows


def novelty(embeddings: np.ndarray, times: List[float], min_dt: float = 120.0) -> np.ndarray:
    """1 minus the similarity to the most similar frame at least ``min_dt`` seconds away: high = unlike the rest."""
    if len(embeddings) == 0:
        return np.zeros(0)
    similarity = embeddings @ embeddings.T
    t = np.asarray(times, dtype=np.float64)
    far = np.abs(t[:, None] - t[None, :]) >= min_dt
    best = np.where(far, similarity, -1.0).max(axis=1)
    best = np.where(best < -0.5, 1.0, best)  # nothing far enough away: not novel
    return (1.0 - best).astype(float)


class AudioTagger:
    SR = 32000

    def __init__(self) -> None:
        import torch
        from panns_inference.config import labels
        from panns_inference.models import Cnn14

        self.torch = torch
        self.dev = device()
        self.model = Cnn14(sample_rate=self.SR, window_size=1024, hop_size=320, mel_bins=64,
                           fmin=50, fmax=14000, classes_num=len(labels))
        checkpoint = torch.load(str(PANNS_CKPT), map_location="cpu", weights_only=False)
        self.model.load_state_dict(checkpoint["model"])
        self.model = self.model.to(self.dev).eval()
        self.index = {label: (labels.index(label), weight) for label, weight in SOUNDS.items() if label in labels}

    def tag_file(self, media: Path, chunk: float = 5.0, batch: int = 16, limit: Optional[float] = None) -> List[Dict[str, Any]]:
        """Stream the audio through ffmpeg in ``chunk``-second pieces: [{t, score, top}] with t = piece middle."""
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(media)]
        if limit:
            command += ["-t", f"{limit:.2f}"]
        command += ["-vn", "-ac", "1", "-ar", str(self.SR), "-f", "s16le", "-"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        size = int(self.SR * chunk)
        out: List[Dict[str, Any]] = []
        buffer: List[np.ndarray] = []
        starts: List[float] = []
        count = 0
        try:
            while True:
                raw = process.stdout.read(size * 2)
                if not raw:
                    break
                samples = np.frombuffer(raw[: len(raw) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
                if len(samples) < size // 2:
                    break
                if len(samples) < size:
                    samples = np.pad(samples, (0, size - len(samples)))
                buffer.append(samples)
                starts.append(count * chunk)
                count += 1
                if len(buffer) == batch:
                    out += self._run(buffer, starts, chunk)
                    buffer, starts = [], []
            if buffer:
                out += self._run(buffer, starts, chunk)
        finally:
            process.stdout.close()
            process.wait()
        return out

    def _run(self, buffer: List[np.ndarray], starts: List[float], chunk: float) -> List[Dict[str, Any]]:
        batch = self.torch.from_numpy(np.stack(buffer)).to(self.dev)
        with self.torch.no_grad():
            probs = self.model(batch, None)["clipwise_output"].float().cpu().numpy()
        rows = []
        for start, row in zip(starts, probs):
            hits = {label: float(row[i]) for label, (i, _) in self.index.items() if row[i] >= 0.08}
            score = max([float(row[i]) * weight for _, (i, weight) in self.index.items()] or [0.0])
            rows.append({"t": round(start + chunk / 2, 2), "score": round(score, 3),
                         "top": dict(sorted(hits.items(), key=lambda kv: -kv[1])[:4])})
        return rows


def sound_at(tags: List[Dict[str, Any]], t: float, radius: float = 10.0) -> Dict[str, Any]:
    """The strongest sound event within ``radius`` seconds of ``t``."""
    best: Dict[str, Any] = {"score": 0.0, "top": {}}
    for tag in tags:
        if abs(tag["t"] - t) <= radius and tag["score"] > best["score"]:
            best = tag
    return best


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    part = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as handle:
        shutil.copyfileobj(response, handle, 1 << 20)
    part.replace(destination)


def download_models() -> None:
    """Fetch the weights once (about 1 GB): PANNs labels and checkpoint, then the OpenCLIP model."""
    _download(LABEL_URL, PANNS_LABELS)
    _download(CKPT_URL, PANNS_CKPT)
    import open_clip

    open_clip.create_model_and_transforms(CLIP_ARCH, pretrained=CLIP_TAG, cache_dir=str(MODELS / "clip"))


if __name__ == "__main__":
    download_models()
    print("Models ready in", MODELS)
