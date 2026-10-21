"""Burn camera controls and trajectory telemetry into generated video frames."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


@dataclass(frozen=True)
class CameraPose:
    t: float
    position: np.ndarray
    quaternion: np.ndarray


@dataclass(frozen=True)
class CameraKeyEvent:
    t: float
    code: str
    pressed: bool


@dataclass(frozen=True)
class CameraOverlay:
    name: str
    duration_ms: float
    poses: tuple[CameraPose, ...]
    key_events: tuple[CameraKeyEvent, ...]


@dataclass(frozen=True)
class OverlaySegment:
    start: int
    end: int
    has_camera: bool
    user_prompt: str


def video_overlays_enabled() -> bool:
    value = os.environ.get("NOMAS_BURN_VIDEO_OVERLAYS")
    return value is not None and value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def parse_camera_overlay(value: str | None, fps: float) -> CameraOverlay | None:
    """Parse the browser camera-trajectory JSON used for model conditioning."""
    if not value or not value.strip():
        return None
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("frames"), list):
        return None

    sample_rate = _positive_float(payload.get("sampleRate"), fps)
    poses: list[CameraPose] = []
    for index, raw in enumerate(payload["frames"]):
        if not isinstance(raw, dict):
            continue
        position = raw.get("position")
        quaternion = raw.get("quaternion")
        if not isinstance(position, dict) or not isinstance(quaternion, dict):
            continue
        try:
            position_array = np.array(
                [position["x"], position["y"], position["z"]],
                dtype=np.float64,
            )
            quaternion_array = np.array(
                [
                    quaternion["x"],
                    quaternion["y"],
                    quaternion["z"],
                    quaternion["w"],
                ],
                dtype=np.float64,
            )
            timestamp = float(raw.get("t", index * 1000.0 / sample_rate))
        except (KeyError, TypeError, ValueError):
            continue
        norm = float(np.linalg.norm(quaternion_array))
        if (
            not np.isfinite(position_array).all()
            or not np.isfinite(quaternion_array).all()
            or not math.isfinite(timestamp)
            or norm < 1e-8
        ):
            continue
        poses.append(
            CameraPose(
                t=timestamp,
                position=position_array,
                quaternion=quaternion_array / norm,
            )
        )
    if not poses:
        return None

    poses.sort(key=lambda pose: pose.t)
    inferred_duration = max(
        1000.0 / sample_rate,
        poses[-1].t - poses[0].t + 1000.0 / sample_rate,
    )
    duration_ms = _positive_float(payload.get("durationMs"), inferred_duration)
    supported_keys = {
        "KeyW",
        "KeyA",
        "KeyS",
        "KeyD",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
    }
    key_events: list[CameraKeyEvent] = []
    raw_key_events = payload.get("keyEvents")
    if isinstance(raw_key_events, list):
        for raw in raw_key_events:
            if not isinstance(raw, dict):
                continue
            try:
                timestamp = float(raw["t"])
                code = str(raw["code"])
            except (KeyError, TypeError, ValueError):
                continue
            if (
                not math.isfinite(timestamp)
                or timestamp < 0
                or code not in supported_keys
            ):
                continue
            key_events.append(
                CameraKeyEvent(
                    t=timestamp,
                    code=code,
                    pressed=raw.get("pressed") is True,
                )
            )
    key_events.sort(key=lambda event: event.t)
    return CameraOverlay(
        name=str(payload.get("name") or "Camera path"),
        duration_ms=duration_ms,
        poses=tuple(poses),
        key_events=tuple(key_events),
    )


def burn_camera_overlay(
    frames: np.ndarray,
    camera_trajectory: str | None,
    fps: float,
) -> np.ndarray:
    """Return RGB uint8 frames with camera telemetry permanently composited."""
    overlay = parse_camera_overlay(camera_trajectory, fps)
    if overlay is None or frames.ndim != 4 or frames.shape[-1] != 3:
        return frames

    output = np.ascontiguousarray(frames.copy())
    frame_count = int(output.shape[0])
    if frame_count == 0:
        return output

    for frame_index in range(frame_count):
        progress = frame_index / max(frame_count - 1, 1) if frame_count > 1 else 0.0
        pose_index = _pose_index_at_progress(
            overlay.poses, overlay.duration_ms, progress
        )
        actions = _actions_at_time(
            overlay.key_events,
            progress * overlay.duration_ms,
        )
        # OpenCV accepts RGB arrays, but color tuples are written channel-wise;
        # use RGB tuples consistently because imageio receives RGB afterward.
        _draw_overlay_frame(
            output[frame_index],
            overlay,
            pose_index,
            progress,
            actions,
        )
    return output


def burn_video_overlays(
    frames: np.ndarray,
    camera_trajectory: str | None,
    fps: float,
    *,
    user_prompts: Sequence[str] | None = None,
    segment_boundaries: Sequence[int] | None = None,
    segment_has_camera: Sequence[bool] | None = None,
    timeline_frame_offset: int = 0,
    timeline_frame_count: int | None = None,
) -> np.ndarray:
    """Burn camera or original-user-text HUDs onto their matching segments."""
    if frames.ndim != 4 or frames.shape[-1] != 3 or not len(frames):
        return frames

    overlay = parse_camera_overlay(camera_trajectory, fps)
    segments = _overlay_segments(
        len(frames),
        user_prompts,
        segment_boundaries,
        segment_has_camera,
        overlay is not None,
    )
    if not segments:
        return burn_camera_overlay(frames, camera_trajectory, fps)

    output = np.ascontiguousarray(frames.copy())
    for segment in segments:
        length = max(1, segment.end - segment.start)
        current_kind = _segment_kind(segment)
        for frame_index in range(segment.start, segment.end):
            local_index = frame_index - segment.start
            if timeline_frame_count is not None and len(segments) == 1:
                progress = (timeline_frame_offset + local_index) / max(
                    int(timeline_frame_count) - 1, 1
                )
                progress = min(1.0, max(0.0, progress))
            else:
                progress = local_index / max(length - 1, 1)
            if current_kind == "camera" and overlay is not None:
                pose_index = _pose_index_at_progress(
                    overlay.poses,
                    overlay.duration_ms,
                    progress,
                )
                _draw_overlay_frame(
                    output[frame_index],
                    overlay,
                    pose_index,
                    progress,
                    _actions_at_time(
                        overlay.key_events,
                        progress * overlay.duration_ms,
                    ),
                )
            elif current_kind == "text":
                _draw_text_overlay_frame(
                    output[frame_index],
                    segment.user_prompt,
                    progress,
                )
    return output


def burn_shared_overlay_video(
    source: str | Path,
    destination: str | Path,
    overlay: Dict[str, Any],
) -> Dict[str, Any]:
    """Render the share-page prompt/camera timeline into a downloadable MP4.

    Frames are processed one at a time so exporting a long cumulative World
    does not require holding the complete video in host memory.
    """
    import imageio.v2 as imageio

    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    raw_turns = overlay.get("turns") if isinstance(overlay, dict) else None
    turns = [dict(turn) for turn in (raw_turns or []) if isinstance(turn, dict)]
    turns.sort(
        key=lambda turn: (
            float(turn.get("start_seconds") or 0.0),
            int(turn.get("number") or 0),
        )
    )
    theme = str(overlay.get("theme") or "dark").strip().lower()
    if theme not in {"dark", "light"}:
        theme = "dark"

    reader = imageio.get_reader(str(source_path))
    writer = None
    frame_count = 0
    try:
        metadata = reader.get_meta_data()
        fps = _positive_float(metadata.get("fps"), 24.0)
        writer = imageio.get_writer(
            str(destination_path),
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=None,
            ffmpeg_log_level="error",
            output_params=[
                "-preset",
                "ultrafast",
                "-crf",
                "21",
                "-movflags",
                "+faststart",
            ],
        )
        parsed_cameras: dict[int, CameraOverlay | None] = {}
        active_turn_index = 0
        for frame_index, frame in enumerate(reader):
            image = np.ascontiguousarray(frame[..., :3])
            timestamp = frame_index / fps
            while active_turn_index + 1 < len(turns) and timestamp >= float(
                turns[active_turn_index + 1].get("start_seconds") or 0.0
            ):
                active_turn_index += 1
            turn = turns[active_turn_index] if turns else None
            if turn is not None:
                start = float(turn.get("start_seconds") or 0.0)
                end = float(turn.get("end_seconds") or start)
                if start <= timestamp <= end:
                    progress = min(
                        1.0,
                        max(0.0, (timestamp - start) / max(end - start, 1 / fps)),
                    )
                    camera_value = turn.get("camera")
                    if isinstance(camera_value, dict):
                        key = id(turn)
                        if key not in parsed_cameras:
                            parsed_cameras[key] = parse_camera_overlay(
                                json.dumps(
                                    {
                                        **camera_value,
                                        "durationMs": camera_value.get("duration_ms"),
                                        "sampleRate": camera_value.get("sample_rate"),
                                        "keyEvents": camera_value.get("key_events"),
                                    },
                                    ensure_ascii=False,
                                ),
                                fps,
                            )
                        camera = parsed_cameras[key]
                        if camera is not None:
                            pose_index = _pose_index_at_progress(
                                camera.poses,
                                camera.duration_ms,
                                progress,
                            )
                            _draw_overlay_frame(
                                image,
                                camera,
                                pose_index,
                                progress,
                                _actions_at_time(
                                    camera.key_events,
                                    progress * camera.duration_ms,
                                ),
                                turn_number=int(turn.get("number") or 1),
                                theme=theme,
                            )
                    else:
                        prompt = str(turn.get("prompt") or "").strip()
                        if prompt:
                            _draw_text_overlay_frame(
                                image,
                                prompt,
                                progress,
                                turn_number=int(turn.get("number") or 1),
                                theme=theme,
                            )
            writer.append_data(image)
            frame_count += 1
    finally:
        reader.close()
        if writer is not None:
            writer.close()

    return {
        "frames": frame_count,
        "fps": fps,
        "duration_seconds": frame_count / fps if fps > 0 else 0.0,
    }


def _segment_kind(segment: OverlaySegment) -> str:
    if segment.has_camera:
        return "camera"
    if segment.user_prompt:
        return "text"
    return "none"


def _overlay_segments(
    frame_count: int,
    user_prompts: Sequence[str] | None,
    boundaries: Sequence[int] | None,
    camera_flags: Sequence[bool] | None,
    has_camera_overlay: bool,
) -> list[OverlaySegment]:
    prompts = [str(value).strip() for value in (user_prompts or [])]
    flags = [bool(value) for value in (camera_flags or [])]
    if (
        not boundaries
        or len(boundaries) < 2
        or int(boundaries[0]) != 0
        or any(
            int(right) <= int(left) for left, right in zip(boundaries, boundaries[1:])
        )
    ):
        if prompts or has_camera_overlay:
            return [
                OverlaySegment(
                    0,
                    frame_count,
                    bool(has_camera_overlay),
                    prompts[0] if prompts else "",
                )
            ]
        return []

    source_end = int(boundaries[-1])
    if source_end <= 0:
        return []
    segment_count = len(boundaries) - 1
    segments: list[OverlaySegment] = []
    for index in range(segment_count):
        start = int(round(int(boundaries[index]) * frame_count / source_end))
        end = int(round(int(boundaries[index + 1]) * frame_count / source_end))
        start = max(0, min(frame_count, start))
        end = max(start + 1, min(frame_count, end))
        segments.append(
            OverlaySegment(
                start=start,
                end=end,
                has_camera=(flags[index] if index < len(flags) else has_camera_overlay),
                user_prompt=prompts[index] if index < len(prompts) else "",
            )
        )
    if segments:
        segments[-1] = OverlaySegment(
            segments[-1].start,
            frame_count,
            segments[-1].has_camera,
            segments[-1].user_prompt,
        )
    return segments


def _font_candidates() -> list[str]:
    configured = os.environ.get("NOMAS_OVERLAY_FONT")
    return [
        value
        for value in (
            configured,
            str(
                Path(__file__).resolve().parent
                / "frontend"
                / "public"
                / "fonts"
                / "Tencent-W7CN.woff2"
            ),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        if value
    ]


@lru_cache(maxsize=32)
def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = _font_candidates()
    if bold:
        candidates = [
            value.replace("Regular", "Bold").replace(".ttf", "-Bold.ttf")
            for value in candidates
        ] + candidates
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    text_font: ImageFont.ImageFont,
) -> int:
    box = draw.textbbox((0, 0), text, font=text_font)
    return int(box[2] - box[0])


def _wrap_prompt(
    draw: ImageDraw.ImageDraw,
    prompt: str,
    text_font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int = 4,
) -> list[str]:
    words = prompt.replace("\r", "").split()
    if not words:
        return []
    # Languages without spaces still wrap naturally at character boundaries.
    tokens = words if len(words) > 1 else list(words[0])
    separator = " " if len(words) > 1 else ""
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = f"{current}{separator if current else ''}{token}"
        if _text_width(draw, candidate, text_font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = token
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    consumed = separator.join(lines)
    if len(consumed) < len(prompt.strip()) and lines:
        ellipsis = "…"
        while (
            lines[-1]
            and _text_width(
                draw,
                lines[-1] + ellipsis,
                text_font,
            )
            > max_width
        ):
            lines[-1] = lines[-1][:-1].rstrip()
        lines[-1] += ellipsis
    return lines


def _draw_text_overlay_frame(
    image: np.ndarray,
    prompt: str,
    progress: float,
    *,
    turn_number: int = 1,
    theme: str = "dark",
) -> None:
    layout = _draw_shared_overlay_shell(
        image,
        progress,
        "REAL USER PROMPT",
        turn_number=turn_number,
        theme=theme,
    )
    width = image.shape[1]
    left, top, panel_width, _, title_height, pad, _ = layout
    prompt_layer = _cached_prompt_layer(
        image.shape[1],
        image.shape[0],
        prompt,
        theme,
        left,
        top,
        panel_width,
        title_height,
        pad,
    )
    _composite_rgba_array(image, prompt_layer)


def _overlay_panel_geometry(
    image: np.ndarray,
    *,
    camera: bool = False,
) -> tuple[int, int, int, int, int, int, int]:
    """Return the one canonical right-top overlay geometry for every mode."""
    height, width = image.shape[:2]
    scale = max(0.62, min(width / 1280.0, height / 704.0))
    margin = max(12, min(22, int(round(width * 0.015))))
    panel_width = min(int(round(390 * scale)), max(210, width - margin * 2))
    desired_height = 254 if camera else 154
    panel_height = min(
        int(round(desired_height * scale)),
        max(100, height - margin * 2),
    )
    left = width - margin - panel_width
    top = margin
    title_height = max(26, int(round(43 * scale)))
    pad = max(12, int(round(20 * scale)))
    progress_height = max(2, int(round(3 * scale)))
    return (
        left,
        top,
        panel_width,
        panel_height,
        title_height,
        pad,
        progress_height,
    )


def _draw_shared_overlay_shell(
    image: np.ndarray,
    progress: float,
    mode: str,
    *,
    turn_number: int = 1,
    theme: str = "dark",
) -> tuple[int, int, int, int, int, int, int]:
    """Draw the exact same shell for text and camera overlay contents."""
    width = image.shape[1]
    camera = mode == "CAMERA PATH"
    (
        left,
        top,
        panel_width,
        panel_height,
        title_height,
        pad,
        progress_height,
    ) = _overlay_panel_geometry(image, camera=camera)
    scale = max(0.62, min(width / 1280.0, image.shape[0] / 704.0))
    dark = theme != "light"
    accent = (185, 228, 127) if dark else (113, 138, 85)
    shell = _cached_hud_shell(
        image.shape[1],
        image.shape[0],
        camera,
        mode,
        max(1, int(turn_number)),
        theme,
    )
    _composite_rgba_array(image, shell)

    bar_left = left + pad
    bar_right = left + panel_width - pad
    bar_top = top + panel_height - _scaled(8, width, 6)
    cv2.rectangle(
        image,
        (bar_left, bar_top),
        (bar_right, bar_top + progress_height),
        (66, 62, 54) if not dark else (60, 75, 71),
        -1,
    )
    progress = min(1.0, max(0.0, progress))
    progress_right = bar_left + max(
        progress_height,
        int(round((bar_right - bar_left) * progress)),
    )
    cv2.rectangle(
        image,
        (bar_left, bar_top),
        (min(bar_right, progress_right), bar_top + progress_height),
        accent,
        -1,
    )
    return (
        left,
        top,
        panel_width,
        panel_height,
        title_height,
        pad,
        progress_height,
    )


@lru_cache(maxsize=24)
def _cached_hud_shell(
    width: int,
    height: int,
    camera: bool,
    mode: str,
    turn_number: int,
    theme: str,
) -> np.ndarray:
    dummy = np.empty((height, width, 3), dtype=np.uint8)
    (
        left,
        top,
        panel_width,
        panel_height,
        title_height,
        pad,
        _,
    ) = _overlay_panel_geometry(dummy, camera=camera)
    scale = max(0.62, min(width / 1280.0, height / 704.0))
    dark = theme != "light"
    accent = (185, 228, 127) if dark else (113, 138, 85)
    border = (203, 218, 186) if dark else (65, 61, 53)
    start_color = np.array((35, 39, 31) if dark else (255, 254, 251))
    end_color = np.array((23, 26, 21) if dark else (243, 236, 223))
    text_color = (240, 237, 229) if dark else (62, 58, 51)
    muted_color = (149, 143, 132) if dark else (95, 90, 81)
    rule_color = (221, 231, 208) if dark else (78, 73, 63)
    radius = max(10, int(round(18 * scale)))

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    shadow_draw.rounded_rectangle(
        (
            left,
            top + max(4, int(round(9 * scale))),
            left + panel_width,
            top + panel_height + max(4, int(round(9 * scale))),
        ),
        radius=radius,
        fill=(8, 10, 8, 95),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(4, int(round(12 * scale)))))
    layer = Image.alpha_composite(layer, shadow)

    gradient = np.zeros((panel_height, panel_width, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:panel_height, 0:panel_width]
    blend = (xx + yy) / max(panel_width + panel_height - 2, 1)
    for channel in range(3):
        gradient[:, :, channel] = np.rint(
            start_color[channel] * (1.0 - blend) + end_color[channel] * blend
        ).astype(np.uint8)
    gradient[:, :, 3] = 247 if dark else 248
    panel = Image.fromarray(gradient, "RGBA")
    mask = Image.new("L", (panel_width, panel_height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, panel_width - 1, panel_height - 1),
        radius=radius,
        fill=255,
    )
    layer.paste(panel, (left, top), mask)
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.rounded_rectangle(
        (left, top, left + panel_width, top + panel_height),
        radius=radius,
        outline=(*border, 98 if dark else 178),
        width=max(1, int(round(scale))),
    )

    icon_size = max(20, int(round(26 * scale)))
    icon_left = left + pad
    icon_top = top + max(4, int(round(8 * scale)))
    draw.ellipse(
        (
            icon_left,
            icon_top,
            icon_left + icon_size,
            icon_top + icon_size,
        ),
        fill=(*accent, 255) if dark else (45, 44, 39, 255),
    )
    icon_color = (25, 32, 16, 255) if dark else (255, 253, 248, 255)
    icon_center = (icon_left + icon_size // 2, icon_top + icon_size // 2)
    icon_radius = max(4, int(round(7 * scale)))
    draw.polygon(
        [
            (icon_center[0] + icon_radius, icon_center[1] - icon_radius),
            (icon_center[0] + icon_radius // 3, icon_center[1] + icon_radius),
            (icon_center[0], icon_center[1] + icon_radius // 3),
            (icon_center[0] - icon_radius, icon_center[1] + icon_radius),
        ],
        fill=icon_color,
    )

    label_x = icon_left + icon_size + max(7, int(round(9 * scale)))
    small_font = _load_font(max(9, int(round(10 * scale))), bold=True)
    strong_font = _load_font(max(10, int(round(11 * scale))), bold=True)
    state_font = _load_font(max(8, int(round(9 * scale))), bold=True)
    draw.text(
        (label_x, top + max(3, int(round(5 * scale)))),
        mode,
        font=small_font,
        fill=(*accent, 255) if dark else (64, 95, 41, 255),
    )
    draw.text(
        (label_x, top + max(16, int(round(19 * scale)))),
        f"Turn {turn_number:02d}",
        font=strong_font,
        fill=(*text_color, 255),
    )

    button_size = max(23, int(round(29 * scale)))
    button_right = left + panel_width - pad
    button_left = button_right - button_size
    button_top = top + max(2, (title_height - button_size) // 2)
    draw.ellipse(
        (
            button_left,
            button_top,
            button_right,
            button_top + button_size,
        ),
        fill=(25, 29, 23, 225) if dark else (255, 253, 248, 235),
        outline=(75, 85, 66, 220) if dark else (68, 64, 56, 108),
        width=max(1, int(round(scale))),
    )
    eye_center = (
        button_left + button_size // 2,
        button_top + button_size // 2,
    )
    eye_w = max(7, int(round(9 * scale)))
    eye_h = max(4, int(round(5 * scale)))
    eye_color = (215, 211, 202, 255) if dark else (55, 52, 46, 255)
    draw.ellipse(
        (
            eye_center[0] - eye_w,
            eye_center[1] - eye_h,
            eye_center[0] + eye_w,
            eye_center[1] + eye_h,
        ),
        outline=eye_color,
        width=max(1, int(round(1.4 * scale))),
    )
    draw.line(
        (
            eye_center[0] - eye_w,
            eye_center[1] - eye_h - 1,
            eye_center[0] + eye_w,
            eye_center[1] + eye_h + 1,
        ),
        fill=eye_color,
        width=max(1, int(round(1.8 * scale))),
    )

    state = "PLAYBACK"
    state_width = _text_width(draw, state, state_font)
    state_right = button_left - max(7, int(round(9 * scale)))
    state_x = state_right - state_width
    draw.text(
        (state_x, top + max(11, int(round(16 * scale)))),
        state,
        font=state_font,
        fill=(*muted_color, 255),
    )
    status_dot = max(2, int(round(2.5 * scale)))
    draw.ellipse(
        (
            state_x - status_dot * 3,
            top + title_height // 2 - status_dot,
            state_x - status_dot,
            top + title_height // 2 + status_dot,
        ),
        fill=(*muted_color, 255),
    )
    draw.line(
        (
            left + pad,
            top + title_height,
            left + panel_width - pad,
            top + title_height,
        ),
        fill=(*rule_color, 86 if dark else 100),
        width=max(1, int(round(scale))),
    )
    corner = max(12, int(round(17 * scale)))
    line_width = max(1, int(round(2 * scale)))
    draw.line(
        (left, top + corner, left, top + radius),
        fill=(*accent, 255),
        width=line_width,
    )
    draw.line(
        (left + radius, top, left + corner * 2, top),
        fill=(*accent, 255),
        width=line_width,
    )
    draw.line(
        (
            left + panel_width - corner * 2,
            top + panel_height,
            left + panel_width - radius,
            top + panel_height,
        ),
        fill=(*accent, 255),
        width=line_width,
    )
    draw.line(
        (
            left + panel_width,
            top + panel_height - radius,
            left + panel_width,
            top + panel_height - corner,
        ),
        fill=(*accent, 255),
        width=line_width,
    )

    if camera:
        body_left = left + pad - max(4, int(round(7 * scale)))
        body_top = top + title_height + max(5, int(round(9 * scale)))
        body_right = left + panel_width - pad + max(4, int(round(7 * scale)))
        body_bottom = top + panel_height - max(10, int(round(17 * scale)))
        body_radius = max(5, int(round(8 * scale)))
        draw.rounded_rectangle(
            (body_left, body_top, body_right, body_bottom),
            radius=body_radius,
            fill=(12, 19, 19, 225),
            outline=(111, 105, 93, 56),
            width=max(1, int(round(scale))),
        )
        footer_height = max(24, int(round(32 * scale)))
        draw.line(
            (
                body_left,
                body_bottom - footer_height,
                body_right,
                body_bottom - footer_height,
            ),
            fill=(255, 255, 255, 21),
            width=1,
        )

    return np.asarray(layer)


@lru_cache(maxsize=32)
def _cached_prompt_layer(
    width: int,
    height: int,
    prompt: str,
    theme: str,
    left: int,
    top: int,
    panel_width: int,
    title_height: int,
    pad: int,
) -> np.ndarray:
    scale = max(0.62, min(width / 1280.0, height / 704.0))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    body_font = _load_font(max(14, int(round(20 * scale))), bold=False)
    lines = _wrap_prompt(
        draw,
        prompt,
        body_font,
        panel_width - pad * 2,
        max_lines=3,
    )
    line_height = max(18, int(round(26 * scale)))
    y = top + title_height + max(8, int(round(12 * scale)))
    body_color = (240, 237, 229, 255) if theme != "light" else (23, 23, 19, 255)
    for line in lines:
        draw.text(
            (left + pad, y),
            line,
            font=body_font,
            fill=body_color,
        )
        y += line_height
    return np.asarray(layer)


def _positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return parsed if math.isfinite(parsed) and parsed > 0 else float(fallback)


def _pose_index_at_progress(
    poses: Sequence[CameraPose],
    duration_ms: float,
    progress: float,
) -> int:
    target = poses[0].t + min(1.0, max(0.0, progress)) * duration_ms
    for index, pose in enumerate(poses):
        if pose.t >= target:
            return index
    return len(poses) - 1


def _quaternion_rotation_matrix(quaternion: np.ndarray) -> np.ndarray:
    x, y, z, w = quaternion
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _yaw_pitch(quaternion: np.ndarray) -> tuple[float, float]:
    rotation = _quaternion_rotation_matrix(quaternion)
    forward = rotation @ np.array([0.0, 0.0, -1.0])
    yaw = math.atan2(-float(forward[0]), -float(forward[2]))
    pitch = math.asin(float(np.clip(forward[1], -1.0, 1.0)))
    return yaw, pitch


def _actions_at_time(
    key_events: Sequence[CameraKeyEvent],
    timestamp_ms: float,
) -> dict[str, bool]:
    actions = {
        "forward": False,
        "backward": False,
        "left": False,
        "right": False,
        "look_up": False,
        "look_down": False,
        "look_left": False,
        "look_right": False,
    }
    action_by_code = {
        "KeyW": "forward",
        "KeyA": "left",
        "KeyS": "backward",
        "KeyD": "right",
        "ArrowUp": "look_up",
        "ArrowDown": "look_down",
        "ArrowLeft": "look_left",
        "ArrowRight": "look_right",
    }
    for event in key_events:
        if event.t > timestamp_ms:
            break
        actions[action_by_code[event.code]] = event.pressed
    return actions


def _scaled(value: float, width: int, minimum: int = 1) -> int:
    return max(minimum, int(round(value * width / 640.0)))


def _blend_rect(
    image: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    x1, y1 = top_left
    x2, y2 = bottom_right
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return
    region = image[y1:y2, x1:x2]
    fill = np.empty_like(region)
    fill[:] = color
    cv2.addWeighted(fill, alpha, region, 1.0 - alpha, 0, dst=region)


def _composite_rgba(image: np.ndarray, layer: Image.Image) -> None:
    _composite_rgba_array(image, np.asarray(layer.convert("RGBA")))


def _composite_rgba_array(image: np.ndarray, rgba: np.ndarray) -> None:
    foreground = rgba[:, :, :3].astype(np.float32)
    mask = rgba[:, :, 3:4].astype(np.float32) / 255.0
    image[:] = np.clip(
        image.astype(np.float32) * (1.0 - mask) + foreground * mask,
        0,
        255,
    ).astype(np.uint8)


def _draw_text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    width: int,
    *,
    color: tuple[int, int, int] = (238, 244, 242),
    scale: float = 0.34,
    thickness: int = 1,
) -> None:
    cv2.putText(
        image,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.25, scale * width / 640.0),
        color,
        max(1, thickness),
        cv2.LINE_AA,
    )


def _draw_key_group(
    image: np.ndarray,
    labels: Sequence[str],
    active: Sequence[bool],
    origin_x: int,
    bottom_y: int,
) -> None:
    width = image.shape[1]
    scale = max(0.62, min(width / 1280.0, image.shape[0] / 704.0))
    key = max(22, int(round(32 * scale)))
    gap = max(3, int(round(4 * scale)))
    positions = (
        (origin_x + key + gap, bottom_y - key * 2 - gap),
        (origin_x, bottom_y - key),
        (origin_x + key + gap, bottom_y - key),
        (origin_x + (key + gap) * 2, bottom_y - key),
    )
    for label, enabled, (x, y) in zip(labels, active, positions):
        fill = (70, 145, 235) if enabled else (20, 29, 28)
        border = (230, 244, 255) if enabled else (190, 202, 198)
        _blend_rect(image, (x, y), (x + key, y + key), fill, 0.88 if enabled else 0.72)
        cv2.rectangle(
            image,
            (x, y),
            (x + key, y + key),
            border,
            max(1, _scaled(1, width)),
            cv2.LINE_AA,
        )
        text_size, _ = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.25, 0.30 * width / 640.0),
            1,
        )
        _draw_text(
            image,
            label,
            (
                x + (key - text_size[0]) // 2,
                y + (key + text_size[1]) // 2,
            ),
            width,
            color=(255, 255, 255),
            scale=0.30,
        )


def _draw_arrow_group(
    image: np.ndarray,
    active: Sequence[bool],
    origin_x: int,
    bottom_y: int,
) -> None:
    """Draw rotation controls as up/left/down/right arrow icons."""
    width = image.shape[1]
    scale = max(0.62, min(width / 1280.0, image.shape[0] / 704.0))
    key = max(22, int(round(32 * scale)))
    gap = max(3, int(round(4 * scale)))
    positions = (
        (origin_x + key + gap, bottom_y - key * 2 - gap),
        (origin_x, bottom_y - key),
        (origin_x + key + gap, bottom_y - key),
        (origin_x + (key + gap) * 2, bottom_y - key),
    )
    directions = ("up", "left", "down", "right")
    for direction, enabled, (x, y) in zip(directions, active, positions):
        fill = (70, 145, 235) if enabled else (20, 29, 28)
        border = (230, 244, 255) if enabled else (190, 202, 198)
        icon = (255, 255, 255) if enabled else (213, 225, 221)
        _blend_rect(
            image,
            (x, y),
            (x + key, y + key),
            fill,
            0.88 if enabled else 0.72,
        )
        cv2.rectangle(
            image,
            (x, y),
            (x + key, y + key),
            border,
            max(1, _scaled(1, width)),
            cv2.LINE_AA,
        )

        cx, cy = x + key // 2, y + key // 2
        length = max(3, key // 4)
        wing = max(2, key // 6)
        if direction == "up":
            tail, tip = (cx, cy + length), (cx, cy - length)
            heads = (
                (cx - wing, cy - length + wing),
                (cx + wing, cy - length + wing),
            )
        elif direction == "down":
            tail, tip = (cx, cy - length), (cx, cy + length)
            heads = (
                (cx - wing, cy + length - wing),
                (cx + wing, cy + length - wing),
            )
        elif direction == "left":
            tail, tip = (cx + length, cy), (cx - length, cy)
            heads = (
                (cx - length + wing, cy - wing),
                (cx - length + wing, cy + wing),
            )
        else:
            tail, tip = (cx - length, cy), (cx + length, cy)
            heads = (
                (cx + length - wing, cy - wing),
                (cx + length - wing, cy + wing),
            )
        line_width = max(1, _scaled(1.2, width))
        cv2.line(image, tail, tip, icon, line_width, cv2.LINE_AA)
        cv2.line(image, tip, heads[0], icon, line_width, cv2.LINE_AA)
        cv2.line(image, tip, heads[1], icon, line_width, cv2.LINE_AA)


def _trajectory_points(
    poses: Sequence[CameraPose],
    left: int,
    top: int,
    width: int,
    height: int,
) -> np.ndarray:
    positions = np.stack([pose.position for pose in poses])
    projector, _, _ = _trajectory_projector(
        positions,
        left,
        top,
        width,
        height,
    )
    return projector(positions)


def _trajectory_projector(
    positions: np.ndarray,
    left: int,
    top: int,
    width: int,
    height: int,
):
    """Match the Three.js preview's perspective camera and look-at framing."""
    minimum = positions.min(axis=0)
    maximum = positions.max(axis=0)
    center = (minimum + maximum) / 2.0
    size = max(float(np.linalg.norm(maximum - minimum)), 1.0)
    eye = center + np.array([size, size * 0.8, size], dtype=np.float64)
    forward = center - eye
    forward /= max(float(np.linalg.norm(forward)), 1e-8)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0]))
    right /= max(float(np.linalg.norm(right)), 1e-8)
    camera_up = np.cross(right, forward)
    camera_up /= max(float(np.linalg.norm(camera_up)), 1e-8)
    focal = 0.5 * height / math.tan(math.radians(42.0) / 2.0)

    def project(points: np.ndarray) -> np.ndarray:
        points = np.atleast_2d(points).astype(np.float64)
        relative = points - eye
        depth = relative @ forward
        depth = np.maximum(depth, 1e-6)
        x = left + width / 2.0 + focal * (relative @ right) / depth
        y = top + height / 2.0 - focal * (relative @ camera_up) / depth
        return np.rint(np.column_stack((x, y))).astype(np.int32)

    return project, minimum, size


def _draw_trajectory_grid(
    image: np.ndarray,
    projector,
    minimum: np.ndarray,
    center: np.ndarray,
    size: float,
) -> None:
    grid_size = size * 2.2
    half = grid_size / 2.0
    grid_y = float(minimum[1] - size * 0.08)
    for offset in np.linspace(-half, half, 9):
        horizontal = projector(
            np.array(
                [
                    [center[0] - half, grid_y, center[2] + offset],
                    [center[0] + half, grid_y, center[2] + offset],
                ]
            )
        )
        vertical = projector(
            np.array(
                [
                    [center[0] + offset, grid_y, center[2] - half],
                    [center[0] + offset, grid_y, center[2] + half],
                ]
            )
        )
        cv2.line(
            image,
            tuple(horizontal[0]),
            tuple(horizontal[1]),
            (38, 44, 45),
            1,
            cv2.LINE_AA,
        )
        cv2.line(
            image,
            tuple(vertical[0]),
            tuple(vertical[1]),
            (38, 44, 45),
            1,
            cv2.LINE_AA,
        )


def _draw_camera_marker(
    image: np.ndarray,
    projector,
    pose: CameraPose,
    size: float,
    line_width: int,
) -> None:
    local_points = (
        np.array(
            [
                [0.0, 0.0, 0.0],
                [-0.065, -0.045, -0.13],
                [0.065, -0.045, -0.13],
                [0.0, 0.0, 0.0],
                [0.065, 0.045, -0.13],
                [-0.065, 0.045, -0.13],
                [0.0, 0.0, 0.0],
                [-0.065, -0.045, -0.13],
                [-0.065, 0.045, -0.13],
                [0.065, 0.045, -0.13],
                [0.065, -0.045, -0.13],
            ],
            dtype=np.float64,
        )
        * size
    )
    world_points = (
        local_points @ _quaternion_rotation_matrix(pose.quaternion).T + pose.position
    )
    marker = projector(world_points)
    cv2.polylines(
        image,
        [marker],
        False,
        (242, 247, 255),
        line_width,
        cv2.LINE_AA,
    )
    cv2.circle(
        image,
        tuple(marker[0]),
        max(2, line_width + 1),
        (105, 180, 255),
        -1,
        cv2.LINE_AA,
    )


def _draw_overlay_frame(
    image: np.ndarray,
    overlay: CameraOverlay,
    pose_index: int,
    progress: float,
    actions: dict[str, bool],
    *,
    turn_number: int = 1,
    theme: str = "dark",
) -> None:
    width = image.shape[1]
    (
        panel_left,
        panel_top,
        panel_width,
        panel_height,
        title_height,
        pad,
        _,
    ) = _draw_shared_overlay_shell(
        image,
        progress,
        "CAMERA PATH",
        turn_number=turn_number,
        theme=theme,
    )

    # Camera mode replaces only the shared shell's content region.
    plot_left = panel_left + pad
    plot_top = panel_top + title_height + _scaled(3, width)
    plot_width = panel_width - pad * 2
    plot_bottom = panel_top + panel_height - _scaled(11, width, 9)
    plot_height = max(1, plot_bottom - plot_top)
    plot = image[
        plot_top : plot_top + plot_height,
        plot_left : plot_left + plot_width,
    ]
    positions = np.stack([pose.position for pose in overlay.poses])
    projector, minimum, trajectory_size = _trajectory_projector(
        positions,
        0,
        0,
        plot_width,
        plot_height,
    )
    center = (minimum + positions.max(axis=0)) / 2.0
    _draw_trajectory_grid(
        plot,
        projector,
        minimum,
        center,
        trajectory_size,
    )
    points = projector(positions)
    if len(points) > 1:
        cv2.polylines(plot, [points], False, (105, 113, 102), 1, cv2.LINE_AA)
        cv2.polylines(
            plot,
            [points[: pose_index + 1]],
            False,
            (200, 242, 89),
            max(1, _scaled(2, width)),
            cv2.LINE_AA,
        )
    radius = max(2, _scaled(3, width))
    cv2.circle(plot, tuple(points[0]), radius, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(plot, tuple(points[-1]), radius, (200, 242, 89), -1, cv2.LINE_AA)
    _draw_camera_marker(
        plot,
        projector,
        overlay.poses[min(pose_index, len(overlay.poses) - 1)],
        trajectory_size,
        max(1, _scaled(1, width)),
    )
    # Action telemetry remains separate from the top-right content card.
    scale = max(0.62, min(width / 1280.0, image.shape[0] / 704.0))
    margin = max(12, int(round(14 * scale)))
    footer_offset = max(46, int(round(76 * scale)))
    keys_bottom = image.shape[0] - footer_offset
    _draw_key_group(
        image,
        ("W", "A", "S", "D"),
        (
            actions["forward"],
            actions["left"],
            actions["backward"],
            actions["right"],
        ),
        margin,
        keys_bottom,
    )
    key = max(22, int(round(32 * scale)))
    gap = max(3, int(round(4 * scale)))
    _draw_arrow_group(
        image,
        (
            actions["look_up"],
            actions["look_left"],
            actions["look_down"],
            actions["look_right"],
        ),
        width - margin - (key * 3 + gap * 2),
        keys_bottom,
    )
    footer_height = max(24, int(round(32 * scale)))
    footer_top = plot_top + max(1, plot_height - footer_height)
    cv2.line(
        image,
        (plot_left, footer_top),
        (plot_left + plot_width, footer_top),
        (48, 58, 54),
        1,
        cv2.LINE_AA,
    )
    layer = Image.new("RGBA", (image.shape[1], image.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    footer_font = _load_font(max(9, int(round(11 * scale))), bold=True)
    footer_y = footer_top + max(5, int(round(7 * scale)))
    path_name = overlay.name
    max_name_width = max(1, plot_width - max(50, int(round(62 * scale))))
    while path_name and _text_width(draw, path_name, footer_font) > max_name_width:
        path_name = path_name[:-1]
    if path_name != overlay.name:
        path_name = path_name.rstrip() + "…"
    draw.text(
        (plot_left + max(7, int(round(10 * scale))), footer_y),
        path_name,
        font=footer_font,
        fill=(190, 199, 194, 255),
    )
    percent = f"{round(min(1.0, max(0.0, progress)) * 100)}%"
    percent_width = _text_width(draw, percent, footer_font)
    draw.text(
        (
            plot_left + plot_width - max(7, int(round(10 * scale))) - percent_width,
            footer_y,
        ),
        percent,
        font=footer_font,
        fill=(217, 239, 188, 255),
    )
    _composite_rgba(image, layer)
