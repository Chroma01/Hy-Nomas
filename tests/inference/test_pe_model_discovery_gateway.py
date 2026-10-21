from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from apps.kimi_k3_prompt_enhancer import EnhancedPrompt, KimiK3Client, OnlinePromptEnhancer
from apps.seg_ar_gateway import create_gateway_app
from apps.seg_ar_job_store import JobStore


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    session = Mock()
    session.get.return_value.json.return_value = {"data": [
        {"id": "org/Model-A"}, {"id": "kimi-k3"},
    ]}
    enhancer = OnlinePromptEnhancer(
        output_dir=tmp_path / "outputs",
        client=KimiK3Client(model="missing-default", session=session),
    )
    monkeypatch.setattr("apps.seg_ar_gateway.persist_pe_turn", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.seg_ar_gateway.persist_pe_failure", lambda *args, **kwargs: None)
    store = JobStore(tmp_path / "jobs.json")
    app = create_gateway_app(
        store, frontend_dir=None, output_dir=tmp_path / "outputs",
        prompt_enhancer=enhancer,
    )
    with TestClient(app) as client:
        yield client, store, enhancer, session


def test_config_exposes_advertised_ids_and_default(gateway):
    client, _, _, session = gateway
    config = client.get("/v1/config").json()
    assert config["prompt_enhancement_enabled"]
    assert config["default_prompt_enhancer_model"] == "org/Model-A"
    assert [option["id"] for option in config["prompt_enhancer_options"]] == [
        "org/Model-A", "kimi-k3",
    ]
    assert all("none" in option["reasoning_effort_options"]
               for option in config["prompt_enhancer_options"])
    client.get("/v1/config")
    assert session.get.call_count == 1


@pytest.mark.parametrize("model", [None, "kimi-k3", "org/Model-A"])
def test_generation_uses_selected_model_effort_and_seed(gateway, model):
    client, store, enhancer, _ = gateway
    calls = []

    def enhance(request, previous_session, *, enhancer_model=None, reasoning_effort=None, seed=None):
        calls.append((enhancer_model, reasoning_effort, seed))
        return EnhancedPrompt(
            prompt='{"segments":[]}', num_frames=120, segment_boundaries=[0, 120],
            session={"session_id": request["session_id"]},
            raw_response='{"segments":[]}', request_id="pe-request",
        )

    enhancer.enhance = enhance
    pe_input = {
        "session_id": "model-discovery-test", "action": "Walk forward",
        "prompt_enhancer_reasoning_effort": "none", "prompt_enhancer_seed": 42,
    }
    if model is not None:
        pe_input["prompt_enhancer_model"] = model
    response = client.post("/v1/generate", json={"pe_input": pe_input})
    assert response.status_code == 202
    record = store.get(response.json()["id"])
    assert record["status"] == "queued"
    expected = model or "org/Model-A"
    assert calls == [(expected, "none", 42)]
    assert record["prompt_enhancement_mode"] == expected


def test_unavailable_model_fails_without_calling_another_model(gateway):
    client, store, enhancer, session = gateway
    enhancer.enhance = Mock()
    response = client.post("/v1/generate", json={"pe_input": {
        "session_id": "unsupported-model-test", "action": "Walk forward",
        "prompt_enhancer_model": "unavailable-model",
    }})
    record = store.get(response.json()["id"])
    assert record["status"] == "failed"
    assert "not advertised" in record["error"]
    enhancer.enhance.assert_not_called()
    session.post.assert_not_called()
