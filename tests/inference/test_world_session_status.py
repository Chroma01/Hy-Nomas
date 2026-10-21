from fastapi.testclient import TestClient

from apps.seg_ar_gateway import create_gateway_app
from apps.seg_ar_job_store import JobStore


def test_session_status_tracks_worker_release_without_renewing_session(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    app = create_gateway_app(
        store, frontend_dir=None, output_dir=tmp_path / "outputs",
    )
    with TestClient(app) as client:
        path = "/v1/sessions/world-idle/status"
        assert client.get(path).json()["status"] == "expired"
        store.submit("generate", {
            "session_id": "world-idle", "preserve_kv_cache": True,
        })
        assert store.claim_next("worker-0") is not None
        before = store.path.read_bytes()
        assert client.get(path).json() == {
            "session_id": "world-idle", "status": "active",
        }
        assert store.path.read_bytes() == before
        store.release_session("world-idle", worker_id="worker-0")
        assert client.get(path).json()["status"] == "expired"
