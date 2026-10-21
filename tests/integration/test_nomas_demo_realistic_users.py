#!/usr/bin/env python3
"""Exercise the Hy-Nomas Demo like two independent people plus one queued user.

The two long-running users intentionally start at different times, request
different turn lengths, and pause for different "thinking" intervals. A third
user submits while both resident workers are occupied, proving that queueing
and later admission work without disturbing either long session.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


USER_A_ACTIONS = [
    "The astronaut walks between tall tomato vines inside a glass greenhouse orbiting Earth.",
    "She kneels beside a leaking irrigation pipe and seals it with a compact repair tool.",
    "She rises and follows a floating maintenance drone toward the far end of the greenhouse.",
    "The greenhouse lights dim as the station enters night and blue Earthlight fills the corridor.",
    "She opens an airlock into a neighboring laboratory filled with slowly rotating plant samples.",
    "The drone projects a warning hologram and she studies a cracked sample chamber.",
    "She replaces the chamber seal while loose droplets of water drift in zero gravity.",
]
USER_B_ACTIONS = [
    "A marine biologist descends beside a coral wall while schools of silver fish circle her.",
    "She pauses over a sea turtle and records notes on the waterproof display attached to her wrist.",
    "The current strengthens, so she follows a guide rope toward a narrow opening in the reef.",
    "She enters a blue underwater cavern where shafts of sunlight reveal drifting particles.",
    "A manta ray glides overhead and she slowly turns the camera upward to follow it.",
    "She collects a loose sensor from the seabed and clips it securely to her equipment belt.",
    "She returns toward the research boat as bubbles rise through the bright surface water.",
]


def request_json(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def submit_turn(
    base_url: str,
    *,
    session_id: str,
    subject: str,
    action: str,
    duration_seconds: float,
    seed: int,
    reset_session: bool,
) -> dict[str, Any]:
    return request_json(
        base_url,
        "/v1/generate",
        payload={
            "pe_input": {
                "session_id": session_id,
                "perspective": "third-person follow",
                "style": "real-world footage",
                "subject": subject,
                "action": action,
                "camera_duration_ms": int(duration_seconds * 1000),
            },
            "session_id": session_id,
            "reset_session": reset_session,
            "seed": seed,
            "user_prompts": [action],
            "segment_has_camera": [False],
            "num_frames": int(round(duration_seconds * 24)),
        },
    )


def wait_job(
    base_url: str,
    job_id: str,
    *,
    timeout_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.time() + timeout_seconds
    states: list[dict[str, Any]] = []
    last_state: tuple[Any, Any] | None = None
    while time.time() < deadline:
        job = request_json(base_url, f"/v1/generate/{job_id}")
        state = (job.get("status"), job.get("queue_position"))
        if state != last_state:
            states.append(
                {
                    "at": time.time(),
                    "status": state[0],
                    "queue_position": state[1],
                    "worker_id": job.get("worker_id"),
                }
            )
            last_state = state
        if state[0] in {"succeeded", "failed", "cancelled"}:
            return job, states
        time.sleep(2)
    raise TimeoutError(f"{job_id} timed out after {timeout_seconds:g}s")


def release_session(base_url: str, session_id: str) -> dict[str, Any]:
    submitted = request_json(
        base_url,
        f"/v1/sessions/{session_id}/release",
        payload={},
    )
    job_id = str(submitted["id"])
    deadline = time.time() + 120
    while time.time() < deadline:
        job = request_json(
            base_url,
            f"/v1/sessions/{session_id}/release/{job_id}",
        )
        if job.get("status") in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(1)
    raise TimeoutError(f"release {session_id} timed out")


def baseline_hashes(path: Path | None) -> list[str]:
    if path is None:
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    return [
        str((job.get("result") or {}).get("latent_sha256") or "")
        for job in report["sequences"]["long"][: len(USER_A_ACTIONS)]
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18084")
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-report")
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--user-b-delay-seconds", type=float, default=7)
    parser.add_argument("--third-user-delay-seconds", type=float, default=20)
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_a_hashes = baseline_hashes(
        Path(args.baseline_report).expanduser().resolve()
        if args.baseline_report
        else None
    )
    report: dict[str, Any] = {
        "started_at": time.time(),
        "base_url": args.base_url,
        "initial_health": request_json(args.base_url, "/health"),
        "users": {"a": [], "b": []},
        "third_user": {},
        "samples": [],
    }
    stop_monitor = threading.Event()
    long_users_done = threading.Event()
    lock = threading.Lock()

    def monitor() -> None:
        while not stop_monitor.wait(2):
            try:
                snapshot = request_json(args.base_url, "/v1/admin/status")
            except Exception as exc:  # noqa: BLE001
                snapshot = {"sample_error": str(exc)}
            with lock:
                report["samples"].append(
                    {
                        "at": time.time(),
                        "queued_jobs": snapshot.get("queued_jobs"),
                        "running_jobs": snapshot.get("running_jobs"),
                        "busy_worker_count": snapshot.get("busy_worker_count"),
                        "resources": snapshot.get("resources"),
                    }
                )

    def run_user(
        *,
        key: str,
        session_id: str,
        subject: str,
        actions: list[str],
        durations: list[float],
        think_times: list[float],
        seed: int,
        start_delay: float,
    ) -> None:
        time.sleep(start_delay)
        for index, (action, duration) in enumerate(
            zip(actions, durations),
            1,
        ):
            submitted_at = time.time()
            submitted = submit_turn(
                args.base_url,
                session_id=session_id,
                subject=subject,
                action=action,
                duration_seconds=duration,
                seed=seed,
                reset_session=index == 1,
            )
            result, states = wait_job(
                args.base_url,
                str(submitted["id"]),
                timeout_seconds=args.timeout_seconds,
            )
            payload = result.get("result") or {}
            row = {
                "turn": index,
                "session_id": session_id,
                "subject": subject,
                "action": action,
                "requested_seconds": duration,
                "submitted_at": submitted_at,
                "finished_at": time.time(),
                "job_id": submitted["id"],
                "status": result.get("status"),
                "worker_id": result.get("worker_id"),
                "states": states,
                "generation_seconds": payload.get("generation_seconds"),
                "frames": payload.get("frames"),
                "duration_seconds": payload.get("duration_seconds"),
                "latent_sha256": payload.get("latent_sha256"),
                "video_url": payload.get("video_url"),
                "metadata_url": payload.get("metadata_url"),
                "stream_init_url": payload.get("stream_init_url"),
                "stream_segment_url": payload.get("stream_segment_url"),
                "error_code": result.get("error_code"),
                "error": result.get("error"),
            }
            if key == "a" and index <= len(expected_a_hashes):
                row["baseline_sha256"] = expected_a_hashes[index - 1]
                row["bit_exact"] = (
                    bool(row["latent_sha256"])
                    and row["latent_sha256"] == row["baseline_sha256"]
                )
            with lock:
                report["users"][key].append(row)
            print(json.dumps({"user": key, **row}), flush=True)
            if row["status"] != "succeeded":
                return
            if index <= len(think_times):
                time.sleep(think_times[index - 1])

    def run_third_user() -> None:
        time.sleep(args.third_user_delay_seconds)
        submitted_at = time.time()
        submitted = submit_turn(
            args.base_url,
            session_id="nomas-realistic-user-c",
            subject="A chef working alone in a quiet restaurant kitchen",
            action=(
                "The chef plates a bowl of noodles and adds herbs with "
                "careful, precise movements."
            ),
            duration_seconds=5,
            seed=909090,
            reset_session=True,
        )
        job_id = str(submitted["id"])
        observed: list[dict[str, Any]] = []
        while not long_users_done.is_set():
            job = request_json(args.base_url, f"/v1/generate/{job_id}")
            observed.append(
                {
                    "at": time.time(),
                    "status": job.get("status"),
                    "queue_position": job.get("queue_position"),
                    "worker_id": job.get("worker_id"),
                }
            )
            if job.get("status") in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(2)
        with lock:
            report["third_user"] = {
                "job_id": job_id,
                "submitted_at": submitted_at,
                "observed_before_release": observed,
            }

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    user_threads = [
        threading.Thread(
            target=run_user,
            kwargs={
                "key": "a",
                "session_id": "nomas-realistic-user-a",
                "subject": (
                    "A female astronaut with a white suit, orange mission "
                    "patches, and a transparent visor inside an orbital "
                    "greenhouse"
                ),
                "actions": USER_A_ACTIONS,
                "durations": [10] * len(USER_A_ACTIONS),
                "think_times": [3, 8, 2, 11, 5, 7],
                "seed": 424242,
                "start_delay": 0,
            },
        ),
        threading.Thread(
            target=run_user,
            kwargs={
                "key": "b",
                "session_id": "nomas-realistic-user-b",
                "subject": (
                    "A marine biologist in a yellow diving suit exploring "
                    "a tropical coral reef"
                ),
                "actions": USER_B_ACTIONS,
                "durations": [8, 12, 7, 11, 9, 13, 10],
                "think_times": [9, 2, 13, 4, 8, 3],
                "seed": 525252,
                "start_delay": args.user_b_delay_seconds,
            },
        ),
    ]
    third_thread = threading.Thread(target=run_third_user)
    for thread in [*user_threads, third_thread]:
        thread.start()
    for thread in user_threads:
        thread.join()
    long_users_done.set()

    releases = {
        "a": release_session(args.base_url, "nomas-realistic-user-a"),
        "b": release_session(args.base_url, "nomas-realistic-user-b"),
    }
    third_thread.join()
    third_job_id = report["third_user"].get("job_id")
    if third_job_id:
        third_result, third_states = wait_job(
            args.base_url,
            str(third_job_id),
            timeout_seconds=args.timeout_seconds,
        )
        report["third_user"].update(
            {
                "result": third_result,
                "states_after_release": third_states,
                "finished_at": time.time(),
            }
        )
        release_session(args.base_url, "nomas-realistic-user-c")

    stop_monitor.set()
    monitor_thread.join(timeout=5)
    report["releases"] = releases
    report["final_admin"] = request_json(
        args.base_url,
        "/v1/admin/status",
    )
    report["finished_at"] = time.time()

    a_rows = report["users"]["a"]
    b_rows = report["users"]["b"]
    all_long_succeeded = all(row["status"] == "succeeded" for row in [*a_rows, *b_rows])
    distinct_workers = (
        len({row["worker_id"] for row in a_rows}) == 1
        and len({row["worker_id"] for row in b_rows}) == 1
        and a_rows
        and b_rows
        and a_rows[0]["worker_id"] != b_rows[0]["worker_id"]
    )
    queue_observed = any(
        item["status"] == "queued"
        for item in report["third_user"].get(
            "observed_before_release",
            [],
        )
    )
    report["assertions"] = {
        "all_long_turns_succeeded": all_long_succeeded,
        "user_a_over_60_seconds": bool(
            a_rows and float(a_rows[-1]["duration_seconds"] or 0) >= 60
        ),
        "user_b_over_60_seconds": bool(
            b_rows and float(b_rows[-1]["duration_seconds"] or 0) >= 60
        ),
        "sessions_sticky_and_distinct": bool(distinct_workers),
        "user_a_all_bit_exact": bool(
            expected_a_hashes
            and len(a_rows) == len(expected_a_hashes)
            and all(row.get("bit_exact") for row in a_rows)
        ),
        "third_user_observed_queue": queue_observed,
        "third_user_eventually_succeeded": (
            (report["third_user"].get("result") or {}).get("status") == "succeeded"
        ),
        "service_healthy_after_test": bool(
            report["final_admin"].get("online_worker_count") == 2
        ),
    }
    report["passed"] = all(report["assertions"].values())
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["assertions"], indent=2), flush=True)
    print(output, flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
