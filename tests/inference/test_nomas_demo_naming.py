#!/usr/bin/env python3
"""CPU-only regression checks for demo identifiers and launcher entry points."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from apps.seg_ar_attempt_archive import UserAttemptArchive
from apps.seg_ar_dispatcher import SESSION_COOKIE, create_dispatcher_app
from apps.seg_ar_gateway import create_gateway_app
from apps.seg_ar_job_store import JobStore
from apps.seg_ar_resource_manager import ResourceManager


class DemoNamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="nomas-naming-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_gateway_presence_and_generation_identity(self) -> None:
        monitor = Mock()
        monitor.snapshot.return_value = {"available": False, "online_users": 1, "gpus": []}
        store = JobStore(self.root / "jobs.json")
        client = TestClient(create_gateway_app(
            store,
            frontend_dir=None,
            output_dir=self.root / "output",
            resource_monitor=monitor,
        ))
        self.addCleanup(client.close)
        response = client.get("/v1/config", headers={
            "X-Nomas-Client-Id": "nomas-browser-test",
        })
        self.assertEqual(response.status_code, 200)
        monitor.touch.assert_called_once_with("nomas-browser-test")
        response = client.post("/v1/generate", json={
            "user_prompts": ["A robot walking through a garden"],
            "num_inference_steps": 6,
        }, headers={
            "X-Nomas-User-Id": quote("test user", safe=""),
            "X-Nomas-Host-Id": "test-host",
        })
        self.assertEqual(response.status_code, 202, response.text)
        record = store.generation_attempt_record(response.json()["id"])
        self.assertEqual(record["state"]["user_id"], "test user")
        self.assertEqual(record["state"]["dispatch_host_id"], "test-host")
        self.assertEqual(response.json()["num_inference_steps"], 6)

    def test_dispatcher_page_and_trusted_identity_headers(self) -> None:
        manager = ResourceManager(
            self.root / "resources.json",
            [{"id": "test-host", "url": "http://127.0.0.1:1"}],
        )
        manager.update_host("test-host", True)
        token, _ = manager.login("test user", page_id="initial-page")
        client = TestClient(create_dispatcher_app(manager, frontend_dir=None))
        self.addCleanup(client.close)
        client.cookies.set(SESSION_COOKIE, token)
        for method, path in [
            ("GET", "/auth/status"),
            ("POST", "/auth/reconnect"),
            ("POST", "/auth/heartbeat"),
        ]:
            page_id = f"nomas-page-{path.rsplit('/', 1)[-1]}"
            response = client.request(method, path, headers={
                "X-Nomas-Page-Id": page_id,
            })
            self.assertEqual(response.status_code, 200, response.text)
            state = json.loads(manager.path.read_text())
            self.assertIn(page_id, state["users"][token]["connected_pages"])

        upstream = Mock()
        upstream.status_code = 200
        upstream.headers = {"content-type": "application/json"}
        upstream.iter_content.return_value = iter([b'{"released":true}'])
        with patch("apps.seg_ar_dispatcher.requests.request", return_value=upstream) as request:
            response = client.post("/v1/sessions/test-world/release")
            self.assertEqual(response.json()["released"], False)
            request.assert_not_called()
            response = client.post("/v1/sessions/test-world/release", headers={
                "X-Nomas-Explicit-Session-Release": "1",
                "X-Nomas-User-Id": "forged-user",
                "X-Nomas-Host-Id": "forged-host",
            })
            self.assertEqual(response.json()["released"], True)
            forwarded = {key.lower(): value for key, value in
                         request.call_args.kwargs["headers"].items()}
            self.assertEqual(forwarded["x-nomas-user-id"], "test%20user")
            self.assertEqual(forwarded["x-nomas-host-id"], "test-host")
            self.assertNotIn("cookie", forwarded)
            self.assertEqual(forwarded["x-nomas-explicit-session-release"], "1")
            upstream.close.assert_called_once()

    def test_attempt_archive_environment(self) -> None:
        directory = self.root / "attempts"
        with patch.dict(os.environ, {"NOMAS_USER_ATTEMPT_DIR": str(directory)}):
            archive = UserAttemptArchive(self.root / "output")
        self.assertEqual(archive.directory, directory.resolve())

    def test_worker_launcher_overrides_and_environment(self) -> None:
        executable_dir = self.root / "bin"
        executable_dir.mkdir()
        capture = self.root / "torchrun.json"
        mock_python = executable_dir / "python"
        mock_python.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "if sys.argv[1:3] != ['-m', 'torch.distributed.run']:\n"
            f" os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"
            "Path(os.environ['NOMAS_TEST_CAPTURE']).write_text(json.dumps({\n"
            " 'argv': sys.argv[1:],\n"
            " 'worker_id': os.environ['NOMAS_WORKER_ID'],\n"
            " 'slot': os.environ['NOMAS_WORKER_SLOT'],\n"
            "}))\n"
        )
        mock_python.chmod(0o755)
        # A system torchrun must not bypass the activated environment.
        system_torchrun = executable_dir / "torchrun"
        system_torchrun.write_text("#!/bin/sh\nexit 99\n")
        system_torchrun.chmod(0o755)
        checkpoint = self.root / "checkpoint.safetensors"
        checkpoint.write_bytes(b"test")
        environment = {
            "PATH": f"{executable_dir}:{os.environ['PATH']}",
            "HOME": os.environ.get("HOME", str(self.root)),
            "DIT_WEIGHT": str(checkpoint),
            "SAVE_PATH": str(self.root / "output"),
            "RUNTIME_DIR": str(self.root / "runtime"),
            "SP_SIZE": "1",
            "WORKER_LOCK": str(self.root / "worker.lock"),
            "NOMAS_WORKER_ID": "nomas-test-worker",
            "NOMAS_WORKER_SLOT": "2",
            "NOMAS_MAX_CONCURRENT_JOBS": "3",
            "NOMAS_TEST_CAPTURE": str(capture),
        }
        result = subprocess.run(
            ["bash", "scripts/inference/run_seg_ar_gpu_worker.sh",
             "inference.infer_steps_video=6",
             f"model.vae.checkpoint={checkpoint}",
             "model.vae.compile_decoder=true"],
            cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        launch = json.loads(capture.read_text())
        self.assertEqual(launch["worker_id"], "nomas-test-worker")
        self.assertEqual(launch["slot"], "2")
        argv = launch["argv"]
        self.assertEqual(argv[:2], ["-m", "torch.distributed.run"])
        self.assertEqual(argv[argv.index("--job-db") + 1], "/tmp/nomas_seg_ar_jobs.json")
        self.assertEqual(argv[argv.index("--worker-max-concurrent-jobs") + 1], "3")
        self.assertIn("inference.infer_steps_video=6", argv)
        self.assertIn(f"model.vae.checkpoint={checkpoint}", argv)
        self.assertIn("model.vae.compile_decoder=true", argv)
        self.assertIn("++model.vae.deepgemm_fp8=true", argv)
        self.assertIn("++inference.seg_ar_segment_vae_decode=true", argv)
        self.assertIn("++model.vae.stable_prefix_streaming=true", argv)
        self.assertIn("++inference.interactive_noise_max_seconds=120", argv)
        self.assertIn("++inference.interactive_noise_hard_max_seconds=180", argv)
        self.assertIn("++inference.interactive_noise_growth_seconds=30", argv)
        environment["NOMAS_WORKER_HOSTS"] = "host-a,host-b"
        environment["NOMAS_PRINT_TOPOLOGY_ONLY"] = "true"
        environment["SP_SIZE"] = "2"
        environment["NPROC_PER_NODE"] = "1"
        result = subprocess.run(
            ["bash", "scripts/inference/start_seg_ar_demo.sh"],
            cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("run_seg_ar_multinode_worker.sh", result.stdout)
        self.assertIn("NOMAS_WORKER_HOSTS=host-a,host-b", result.stdout)
        self.assertIn("RDZV_ID=nomas-seg-ar-sp2-", result.stdout)


class EchoBackend(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({
            "path": self.path,
            "client_id": self.headers.get("X-Nomas-Client-Id"),
            "authorization": self.headers.get("Authorization"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


class ProxyNamingTests(unittest.TestCase):
    def test_renamed_proxy_entries_authentication_and_forwarding(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the HTTP proxy smoke test")
        backend = ThreadingHTTPServer(("127.0.0.1", 0), EchoBackend)
        thread = threading.Thread(target=backend.serve_forever, daemon=True)
        thread.start()
        try:
            for command, prefix in [
                ([sys.executable, "scripts/inference/run_nomas_auth_proxy.py"], "NOMAS_PROXY"),
                (["bash", "scripts/inference/run_nomas_http_proxy.sh"], "NOMAS_HTTP_PROXY"),
            ]:
                with self.subTest(entry=command[-1]):
                    self.check_proxy(command, prefix, backend.server_port, node)
        finally:
            backend.shutdown()
            backend.server_close()
            thread.join(timeout=5)

    def check_proxy(self, command: list[str], prefix: str, backend_port: int, node: str) -> None:
        import socket

        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        credentials = "test:temporary-test-password"
        environment = {
            "PATH": os.environ["PATH"],
            "NODE_BIN": node,
            f"{prefix}_BACKEND": f"http://127.0.0.1:{backend_port}",
            f"{prefix}_HOST": "127.0.0.1",
            f"{prefix}_PORT": str(port),
            "NOMAS_DEMO_USERNAME": "test",
            "NOMAS_DEMO_PASSWORD": credentials.partition(":")[2],
            "NOMAS_DEMO_CREDENTIAL_SHA256": hashlib.sha256(credentials.encode()).hexdigest(),
        }
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    status, _, _ = self.request(port, "/health")
                    self.assertEqual(status, 401)
                    break
                except OSError:
                    if process.poll() is not None:
                        self.fail(f"Proxy exited: {process.stderr.read()}")
                    if time.monotonic() >= deadline:
                        self.fail("Proxy did not start within 30 seconds")
                    time.sleep(0.05)
            authorization = "Basic " + base64.b64encode(credentials.encode()).decode()
            status, body, headers = self.request(port, "/health?probe=1", {
                "Authorization": authorization,
                "X-Nomas-Client-Id": "nomas-proxy-client",
            })
            self.assertEqual(status, 200)
            self.assertEqual(body["path"], "/health?probe=1")
            self.assertEqual(body["client_id"], "nomas-proxy-client")
            self.assertIsNone(body["authorization"])
            self.assertEqual(headers["x-content-type-options"], "nosniff")
            self.assertEqual(self.request(port, "/health", {
                "Authorization": "Basic invalid",
            })[0], 401)
            self.assertEqual(self.request(port, "/share/public-test")[0], 200)
            self.assertEqual(self.request(port, "/share/public-test", method="POST")[0], 401)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            process.stderr.close()

    @staticmethod
    def request(port: int, path: str, headers: dict[str, str] | None = None,
                *, method: str = "GET") -> tuple[int, object, dict[str, str]]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            body = response.read()
            value = json.loads(body) if response.status == 200 else body.decode()
            return response.status, value, {
                key.lower(): value for key, value in response.getheaders()
            }
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
