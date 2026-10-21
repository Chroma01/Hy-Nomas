#!/usr/bin/env python3
"""Prove concurrent users do not change deterministic interactive latents.

Two two-turn sessions first run concurrently on two explicitly pinned worker
replicas. The same sessions are then replayed serially on the same respective
replicas with identical prompts, durations, and seeds. Every final latent must
have an identical SHA-256 digest between the concurrent and serial replay.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.seg_ar_job_store import JobStore
from tests.integration.test_nomas_demo_realistic_users import (
    release_session,
    request_json,
    submit_turn,
    wait_job,
)


CASES = {
    "a": {
        "worker_id": "TENCENT64.site:seg-ar-slot-0",
        "subject": (
            "A female astronaut with a white suit, orange mission patches, "
            "and a transparent visor inside an orbital greenhouse"
        ),
        "actions": [
            (
                "The astronaut walks between tall tomato vines inside a glass "
                "greenhouse orbiting Earth."
            ),
            (
                "She kneels beside a leaking irrigation pipe and seals it "
                "with a compact repair tool."
            ),
        ],
        "durations": [10, 10],
        "seed": 424242,
    },
    "b": {
        "worker_id": "TENCENT64.site:seg-ar-slot-1",
        "subject": (
            "A marine biologist in a yellow diving suit exploring a tropical coral reef"
        ),
        "actions": [
            (
                "A marine biologist descends beside a coral wall while "
                "schools of silver fish circle her."
            ),
            (
                "She pauses over a sea turtle and records notes on the "
                "waterproof display attached to her wrist."
            ),
        ],
        "durations": [8, 12],
        "seed": 525252,
    },
}


def pin_session(store: JobStore, session_id: str, worker_id: str) -> None:
    """Preassign a new test session to one otherwise-idle worker."""
    with store._locked_state(write=True) as state:  # noqa: SLF001
        assigned = state["session_workers"].get(session_id)
        if assigned not in (None, worker_id):
            raise RuntimeError(
                f"session {session_id!r} is assigned to {assigned!r}, not {worker_id!r}"
            )
        state["session_workers"][session_id] = worker_id


def run_sequence(
    base_url: str,
    store: JobStore,
    *,
    label: str,
    mode: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    case = CASES[label]
    session_id = f"nomas-numeric-{mode}-{label}"
    worker_id = str(case["worker_id"])
    pin_session(store, session_id, worker_id)
    rows: list[dict[str, Any]] = []
    try:
        for index, (action, duration) in enumerate(
            zip(case["actions"], case["durations"]),
            1,
        ):
            submitted_at = time.time()
            submitted = submit_turn(
                base_url,
                session_id=session_id,
                subject=str(case["subject"]),
                action=str(action),
                duration_seconds=float(duration),
                seed=int(case["seed"]),
                reset_session=index == 1,
            )
            job, states = wait_job(
                base_url,
                str(submitted["id"]),
                timeout_seconds=timeout_seconds,
            )
            result = job.get("result") or {}
            row = {
                "turn": index,
                "session_id": session_id,
                "job_id": submitted["id"],
                "status": job.get("status"),
                "worker_id": job.get("worker_id"),
                "states": states,
                "submitted_at": submitted_at,
                "finished_at": time.time(),
                "generation_seconds": result.get("generation_seconds"),
                "duration_seconds": result.get("duration_seconds"),
                "frames": result.get("frames"),
                "latent_sha256": result.get("latent_sha256"),
                "video_url": result.get("video_url"),
                "error_code": job.get("error_code"),
                "error": job.get("error"),
            }
            rows.append(row)
            print(
                json.dumps(
                    {"mode": mode, "user": label, **row},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if row["status"] != "succeeded":
                break
    finally:
        try:
            release_session(base_url, session_id)
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "user": label,
                        "cleanup_error": str(exc),
                    }
                ),
                flush=True,
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18084")
    parser.add_argument("--job-db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    store = JobStore(args.job_db)
    health = request_json(args.base_url, "/health")
    if int(health.get("online_worker_count") or 0) != 2:
        raise RuntimeError(f"expected two online workers, got {health}")
    if int(health.get("queued_jobs") or 0) or int(health.get("running_jobs") or 0):
        raise RuntimeError(f"service is not idle before parity test: {health}")

    report: dict[str, Any] = {
        "started_at": time.time(),
        "base_url": args.base_url,
        "initial_health": health,
        "concurrent": {},
        "serial": {},
    }
    lock = threading.Lock()

    def concurrent_user(label: str) -> None:
        rows = run_sequence(
            args.base_url,
            store,
            label=label,
            mode="concurrent",
            timeout_seconds=args.timeout_seconds,
        )
        with lock:
            report["concurrent"][label] = rows

    threads = [
        threading.Thread(target=concurrent_user, args=(label,)) for label in ("a", "b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for label in ("a", "b"):
        report["serial"][label] = run_sequence(
            args.base_url,
            store,
            label=label,
            mode="serial",
            timeout_seconds=args.timeout_seconds,
        )

    comparisons: dict[str, Any] = {}
    for label in ("a", "b"):
        concurrent_rows = report["concurrent"].get(label) or []
        serial_rows = report["serial"].get(label) or []
        comparisons[label] = []
        for turn in range(2):
            concurrent_row = (
                concurrent_rows[turn] if turn < len(concurrent_rows) else {}
            )
            serial_row = serial_rows[turn] if turn < len(serial_rows) else {}
            comparisons[label].append(
                {
                    "turn": turn + 1,
                    "concurrent_sha256": concurrent_row.get("latent_sha256"),
                    "serial_sha256": serial_row.get("latent_sha256"),
                    "bit_exact": bool(
                        concurrent_row.get("latent_sha256")
                        and concurrent_row.get("latent_sha256")
                        == serial_row.get("latent_sha256")
                    ),
                    "same_worker": bool(
                        concurrent_row.get("worker_id")
                        == serial_row.get("worker_id")
                        == CASES[label]["worker_id"]
                    ),
                }
            )
    report["comparisons"] = comparisons
    report["final_admin"] = request_json(args.base_url, "/v1/admin/status")
    report["finished_at"] = time.time()
    report["assertions"] = {
        "all_jobs_succeeded": all(
            len(report[mode].get(label) or []) == 2
            and all(row.get("status") == "succeeded" for row in report[mode][label])
            for mode in ("concurrent", "serial")
            for label in ("a", "b")
        ),
        "same_worker_replay": all(
            comparison["same_worker"]
            for rows in comparisons.values()
            for comparison in rows
        ),
        "all_turns_bit_exact": all(
            comparison["bit_exact"]
            for rows in comparisons.values()
            for comparison in rows
        ),
        "service_healthy_after_test": (
            report["final_admin"].get("online_worker_count") == 2
            and report["final_admin"].get("queued_jobs") == 0
            and report["final_admin"].get("running_jobs") == 0
            and report["final_admin"].get("reserved_session_count") == 0
        ),
    }
    report["passed"] = all(report["assertions"].values())
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "assertions": report["assertions"],
                "comparisons": comparisons,
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
