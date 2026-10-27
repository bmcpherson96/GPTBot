from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


class UnknownState(RuntimeError):
    pass


@dataclass
class Match:
    x: int
    y: int
    score: float
    bounds: tuple[int, int, int, int]


def locate(image: Image.Image, template: Image.Image, threshold=.92, ambiguity_gap=.025) -> Match | None:
    """Translation-tolerant, conservative template matcher. Similarity is not task confidence."""
    source = np.asarray(image.convert("RGB"))
    target = np.asarray(template.convert("RGB"))
    h, w = target.shape[:2]
    if h > source.shape[0] or w > source.shape[1]:
        return None
    if np.std(target.astype(float), axis=(0, 1)).max() < 5:
        raise UnknownState("Low-information visual target; select a distinctive label or icon")
    scores = cv2.matchTemplate(source, target, cv2.TM_CCOEFF_NORMED)
    _, score, _, point = cv2.minMaxLoc(scores)
    if not np.isfinite(score) or score < threshold:
        return None
    x, y = point
    # Remove the local correlation peak, then look for a genuinely different candidate.
    other = scores.copy()
    other[max(0, y-h//2):min(other.shape[0], y+h//2+1), max(0, x-w//2):min(other.shape[1], x+w//2+1)] = -1
    if float(np.max(other)) > max(threshold-.01, score-ambiguity_gap):
        raise UnknownState("Visual target is ambiguous; refusing to choose between candidates")
    return Match(x+w//2, y+h//2, score, (x, y, x+w, y+h))


def materialize(store, version):
    """Only crops of the task's selected, non-excluded training evidence are allowed."""
    w = version["workflow"]
    demos = {d["id"]: d for d in store.evidence(version["task"])}
    if not set(w["sources"]) <= set(demos):
        raise ValueError("Workflow references unavailable training evidence")
    frames = {f["id"]: f for ident in w["sources"] for f in demos[ident]["frames"]}
    folder = store.root / "assets" / version["id"]
    folder.mkdir(parents=True, exist_ok=True)
    for name, target in w["targets"].items():
        if target["frame"] not in frames:
            raise ValueError("Target frame is unavailable or belongs to held-out practice")
        with Image.open(store.root / frames[target["frame"]]["path"]) as image:
            left, top, right, bottom = target["bbox"]
            if right > image.width or bottom > image.height:
                raise ValueError("Target crop exceeds frame dimensions")
            crop = image.crop((left, top, right, bottom)).convert("RGB")
            # Reject patterns which cannot even be located uniquely in their source.
            match = locate(image, crop)
            if match is None:
                raise UnknownState("Target cannot be located in its supporting screenshot")
            crop.save(folder / (name+".png"))
    return {name: Image.open(folder/(name+".png")).convert("RGB") for name in w["targets"]}
