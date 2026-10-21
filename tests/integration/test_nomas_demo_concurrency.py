#!/usr/bin/env python3
"""Drive Hy-Nomas Demo queue, concurrency, long-session, and parity smoke tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SubmittedJob:
    label: str
    job_id: str
    submitted_at: float


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def submit(
    base_url: str,
    *,
    label: str,
    session_id: str,
    subject: str,
    action: str,
    duration_seconds: float,
    fps: int,
    seed: int,
) -> SubmittedJob:
    payload = {
        "pe_input": {
            "session_id": session_id,
            "perspective": "third-person follow",
            "style": "real-world footage",
            "subject": subject,
            "action": action,
            "camera_duration_ms": int(duration_seconds * 1000),
        },
        "session_id": session_id,
        "reset_session": label.endswith("-turn-01"),
        "seed": seed,
        "user_prompts": [action],
        "segment_has_camera": [False],
        "num_frames": int(round(duration_seconds * fps)),
    }
    response = request_json(
        base_url,
        "/v1/generate",
        method="POST",
        payload=payload,
    )
    return SubmittedJob(label, str(response["id"]), time.time())


def wait_job(
    base_url: str,
    job: SubmittedJob,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status = None
    while time.time() < deadline:
        status = request_json(base_url, f"/v1/generate/{job.job_id}")
        current = status.get("status")
        if current != last_status:
            print(
                json.dumps(
                    {
                        "label": job.label,
                        "job_id": job.job_id,
                        "status": current,
                        "queue_position": status.get("queue_position"),
                        "elapsed_seconds": round(time.time() - job.submitted_at, 2),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            last_status = current
        if current in {"succeeded", "failed", "cancelled"}:
            return status
        time.sleep(1.0)
    raise TimeoutError(f"{job.label} timed out after {timeout_seconds:g}s")


def ffprobe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_sequence(
    base_url: str,
    *,
    name: str,
    session_id: str,
    subject: str,
    actions: list[str],
    duration_seconds: float,
    fps: int,
    seed: int,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    results = []
    for index, action in enumerate(actions, 1):
        job = submit(
            base_url,
            label=f"{name}-turn-{index:02d}",
            session_id=session_id,
            subject=subject,
            action=action,
            duration_seconds=duration_seconds,
            fps=fps,
            seed=seed,
        )
        result = wait_job(
            base_url,
            job,
            timeout_seconds=timeout_seconds,
        )
        if result["status"] != "succeeded":
            raise RuntimeError(
                f"{job.label} failed: {result.get('error_code')} {result.get('error')}"
            )
        results.append(result)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18083")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument(
        "--suite",
        choices=("short", "long", "all"),
        default="all",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    health = request_json(args.base_url, "/health")
    config = request_json(args.base_url, "/v1/config")
    report: dict[str, Any] = {
        "started_at": time.time(),
        "base_url": args.base_url,
        "health": health,
        "config": config,
        "sequences": {},
        "concurrent": {},
    }

    if args.suite in {"short", "all"}:
        short = run_sequence(
            args.base_url,
            name="short",
            session_id="nomas-short-human",
            subject=(
                "A red-haired woman in a blue rain jacket exploring an old "
                "coastal lighthouse during a storm"
            ),
            actions=[
                "She enters the lighthouse, wipes rain from her face, and slowly climbs the spiral stairs while the handheld camera follows.",
                "She reaches the lantern room, opens the metal door, and looks across the rough ocean as lightning illuminates the glass.",
                "The camera circles behind her while she switches on the beacon and the warm light sweeps across the sea.",
                "She steps onto the balcony, grips the wet railing, and watches a rescue boat emerge through the fog.",
            ],
            duration_seconds=5,
            fps=args.fps,
            seed=20260906,
            timeout_seconds=args.timeout_seconds,
        )
        report["sequences"]["short"] = short

    if args.suite in {"long", "all"}:
        long_a_actions = [
            "The astronaut walks between tall tomato vines inside a glass greenhouse orbiting Earth.",
            "She kneels beside a leaking irrigation pipe and seals it with a compact repair tool.",
            "She rises and follows a floating maintenance drone toward the far end of the greenhouse.",
            "The greenhouse lights dim as the station enters night and blue Earthlight fills the corridor.",
            "She opens an airlock into a neighboring laboratory filled with slowly rotating plant samples.",
            "The drone projects a warning hologram and she studies a cracked sample chamber.",
            "She replaces the chamber seal while loose droplets of water drift in zero gravity.",
            "The lights return and she carries the repaired sample back through the greenhouse.",
            "She reaches the observation window and watches sunrise spread across Earth below.",
        ]
        report["sequences"]["long"] = run_sequence(
            args.base_url,
            name="long",
            session_id="nomas-long-human",
            subject=(
                "A female astronaut with a white suit, orange mission patches, "
                "and a transparent visor inside an orbital greenhouse"
            ),
            actions=long_a_actions,
            duration_seconds=10,
            fps=args.fps,
            seed=424242,
            timeout_seconds=args.timeout_seconds,
        )

        barrier = threading.Barrier(2)
        concurrent: dict[str, Any] = {}

        def actor(label: str, session_id: str, subject: str, action: str) -> None:
            barrier.wait()
            job = submit(
                args.base_url,
                label=label,
                session_id=session_id,
                subject=subject,
                action=action,
                duration_seconds=5,
                fps=args.fps,
                seed=777,
            )
            concurrent[label] = wait_job(
                args.base_url,
                job,
                timeout_seconds=args.timeout_seconds,
            )

        threads = [
            threading.Thread(
                target=actor,
                args=(
                    "parallel-a-turn-01",
                    "nomas-parallel-a",
                    "A ceramic artist in a sunlit studio",
                    "She centers a lump of clay on a spinning wheel and shapes a tall vase.",
                ),
            ),
            threading.Thread(
                target=actor,
                args=(
                    "parallel-b-turn-01",
                    "nomas-parallel-b",
                    "A wildlife photographer in a misty forest",
                    "He follows a red fox between mossy trees while keeping the camera steady.",
                ),
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for label, result in concurrent.items():
            if result["status"] != "succeeded":
                raise RuntimeError(
                    f"{label} failed: {result.get('error_code')} {result.get('error')}"
                )
        report["concurrent"] = concurrent

    for group in [
        *report["sequences"].values(),
        list(report["concurrent"].values()),
    ]:
        for job in group:
            result = job.get("result") or {}
            relative = str(result.get("video_url") or "")
            if not relative:
                continue
            video_path = output_dir / relative.removeprefix("outputs/")
            if video_path.is_file():
                result["video_sha256"] = sha256(video_path)
                result["ffprobe"] = ffprobe(video_path)

    report["admin"] = request_json(args.base_url, "/v1/admin/status")
    report["finished_at"] = time.time()
    report_path = output_dir / "nomas_demo_concurrency_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(report_path)


if __name__ == "__main__":
    main()
