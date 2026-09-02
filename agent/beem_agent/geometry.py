from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


CORNER_NAMES = ("lt", "rt", "rb", "lb")


def order_quad(points: Iterable[Iterable[float]]) -> np.ndarray:
    """Return four image points ordered LT, RT, RB, LB."""
    pts = np.asarray(list(points), dtype=np.float64)
    if pts.shape != (4, 2):
        raise ValueError("corners must contain exactly four [x, y] points")
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)
    ordered = np.array(
        [pts[np.argmin(sums)], pts[np.argmin(diffs)], pts[np.argmax(sums)], pts[np.argmax(diffs)]],
        dtype=np.float64,
    )
    if len(np.unique(ordered, axis=0)) != 4:
        raise ValueError("corners are degenerate or cannot be ordered")
    return ordered


def insets_to_source_quad(insets: dict[str, list[int]]) -> np.ndarray:
    """Convert firmware 0..500 edge insets to LT, RT, RB, LB source points."""
    lt = insets["lt"]
    rt = insets["rt"]
    rb = insets["rb"]
    lb = insets["lb"]
    return np.array(
        [
            [lt[0] / 500.0, lt[1] / 500.0],
            [1.0 - rt[0] / 500.0, rt[1] / 500.0],
            [1.0 - rb[0] / 500.0, 1.0 - rb[1] / 500.0],
            [lb[0] / 500.0, 1.0 - lb[1] / 500.0],
        ],
        dtype=np.float64,
    )


def source_quad_to_insets(source: np.ndarray) -> dict[str, list[int]]:
    source = np.asarray(source, dtype=np.float64)
    if source.shape != (4, 2):
        raise ValueError("source quad must be LT, RT, RB, LB")
    # Allow small phone-photo edge-estimation overshoot and clamp it below.
    # Larger misses still mean the target lies outside the raw projection.
    if np.any(source < -0.025) or np.any(source > 1.025):
        raise ValueError("target extends outside the projector's uncorrected image; move or resize the projector")
    source = np.clip(source, 0.0, 1.0)
    lt, rt, rb, lb = source
    return {
        "lt": [round(lt[0] * 500), round(lt[1] * 500)],
        "rt": [round((1.0 - rt[0]) * 500), round(rt[1] * 500)],
        "rb": [round((1.0 - rb[0]) * 500), round((1.0 - rb[1]) * 500)],
        "lb": [round(lb[0] * 500), round((1.0 - lb[1]) * 500)],
    }


def solve_insets(
    projection_corners: Iterable[Iterable[float]],
    screen_corners: Iterable[Iterable[float]],
    current_insets: dict[str, list[int]],
) -> dict[str, list[int]]:
    """Map a photographed projected quad into a photographed screen quad.

    The current source quad is known from the firmware insets. A homography maps
    it to the projected quadrilateral in the phone photo. Inverting that mapping
    for the physical screen corners gives the new source crop/keystone points.
    """
    projected = order_quad(projection_corners).astype(np.float32)
    target = order_quad(screen_corners).astype(np.float32)
    source = insets_to_source_quad(current_insets).astype(np.float32)
    photo_from_source = cv2.getPerspectiveTransform(source, projected)
    source_from_photo = np.linalg.inv(photo_from_source)
    desired = cv2.perspectiveTransform(target.reshape(1, 4, 2), source_from_photo).reshape(4, 2)
    return source_quad_to_insets(desired)


@dataclass(frozen=True)
class DetectedQuads:
    screen: np.ndarray
    projection: np.ndarray
    confidence: float


def detect_screen_and_projection(image: np.ndarray) -> DetectedQuads:
    """Find nested screen and projected-image quadrilaterals in a phone photo."""
    if image is None or image.size == 0:
        raise ValueError("image could not be decoded")
    height, width = image.shape[:2]
    scale = min(1.0, 1800.0 / max(height, width))
    work = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 140)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = work.shape[0] * work.shape[1]
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in contours:
        area = abs(cv2.contourArea(contour))
        if area < image_area * 0.025:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        quad = order_quad(approx.reshape(4, 2))
        candidates.append((area, quad))
    candidates.sort(key=lambda item: item[0], reverse=True)
    best: tuple[float, np.ndarray, np.ndarray, float] | None = None
    for outer_area, outer in candidates[:16]:
        outer_center = outer.mean(axis=0)
        for inner_area, inner in candidates[:24]:
            ratio = inner_area / outer_area
            # Canny normally yields two almost-identical contours for a thick
            # frame edge. Reject those so the second quad is the projection,
            # not the frame's inner stroke.
            if not 0.18 < ratio < 0.90:
                continue
            inner_center = inner.mean(axis=0)
            if cv2.pointPolygonTest(outer.astype(np.float32), tuple(inner_center), False) < 0:
                continue
            diag = np.linalg.norm(outer[2] - outer[0]) or 1.0
            center_error = np.linalg.norm(inner_center - outer_center) / diag
            if center_error > 0.22:
                continue
            score = (outer_area / image_area) * (1.0 - center_error) * (0.5 + ratio)
            if best is None or score > best[0]:
                confidence = max(0.0, min(0.99, 0.35 + score))
                best = (score, outer, inner, confidence)
    if best is None:
        raise ValueError(
            "could not confidently detect both rectangles; keep the full screen frame in view, "
            "dim the room, and display the bright correction grid"
        )
    _, screen, projection, confidence = best
    return DetectedQuads(screen / scale, projection / scale, confidence)


def draw_detection(image: np.ndarray, detected: DetectedQuads) -> np.ndarray:
    output = image.copy()
    for quad, color, label in (
        (detected.screen, (0, 255, 0), "screen/frame"),
        (detected.projection, (255, 80, 20), "projected image"),
    ):
        points = np.rint(quad).astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(output, [points], True, color, 5, cv2.LINE_AA)
        x, y = points[0, 0]
        cv2.putText(output, label, (int(x), max(30, int(y) - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return output
