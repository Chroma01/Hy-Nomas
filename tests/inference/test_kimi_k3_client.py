import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests

from apps.kimi_k3_prompt_enhancer import (
    DEFAULT_API_URL,
    DEFAULT_PROMPT_ENHANCER_MODEL,
    KimiK3Client,
    OnlinePromptEnhancer,
    PromptEnhancementError,
    _enhancer_request_snapshot,
    normalize_prompt_enhancer_model,
)


@pytest.fixture(autouse=True)
def clear_credentials(monkeypatch):
    for name in ("PE_API_URL", "PE_MODEL", "PE_API_KEY", "PE_API_TIMEOUT", "PE_API_RETRIES"):
        monkeypatch.delenv(name, raising=False)


def make_session(*, streaming=False):
    response = Mock()
    response.status_code = 200
    response.headers = {
        "Content-Type": "text/event-stream" if streaming else "application/json",
    }
    response.json.return_value = {
        "id": "chatcmpl-test",
        "choices": [{"message": {"content": "OK"}}],
    }
    response.iter_lines.return_value = [
        "data: " + json.dumps({
            "id": "chatcmpl-test",
            "choices": [{"delta": {"reasoning_content": "Think"}}],
        }),
        "data: " + json.dumps({
            "id": "chatcmpl-test",
            "choices": [{"delta": {"content": "OK"}}],
        }),
        'data: {"choices": [], "usage": {"completion_tokens": 1}}',
        "data: [DONE]",
    ]
    session = Mock()
    session.post.return_value = response
    session.get.return_value.json.return_value = {"data": [{"id": "kimi-k3"}]}
    return session


@pytest.mark.parametrize("streaming", [False, True])
def test_openai_without_credentials(streaming):
    session = make_session(streaming=streaming)
    client = KimiK3Client(session=session)
    events = []
    assert client.configured
    assert client.complete(
        [{"role": "user", "content": "Hello"}],
        stream_callback=lambda kind, text: events.append((kind, text)),
        reasoning_effort="none",
        seed=42,
    ) == ("OK", "chatcmpl-test")
    kwargs = session.post.call_args.kwargs
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["json"]["model"] == "Nomas-PE"
    assert "reasoning_effort" not in kwargs["json"]
    assert kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert kwargs["json"]["seed"] == 42
    assert kwargs["stream"] is True
    assert session.post.call_args.args == (DEFAULT_API_URL,)
    assert session.trust_env is False
    if streaming:
        assert events == [("reasoning", "Think"), ("content", "OK")]


@pytest.mark.parametrize("api_key", [None, "test-api-key"])
def test_optional_standard_bearer_token(api_key):
    session = make_session()
    client = KimiK3Client(api_key=api_key, session=session)
    client.complete([])
    headers = session.post.call_args.kwargs["headers"]
    assert headers.get("Authorization") == (
        f"Bearer {api_key}" if api_key else None
    )


def test_default_request_disables_thinking():
    payload = KimiK3Client().request_payload([])
    assert "reasoning_effort" not in payload
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh"])
def test_thinking_request_preserves_selected_effort(effort):
    payload = KimiK3Client().request_payload([], reasoning_effort=effort)
    assert payload["reasoning_effort"] == effort
    assert "chat_template_kwargs" not in payload


def test_environment_selects_openai_client(monkeypatch, tmp_path):
    monkeypatch.setenv("PE_API_URL", "http://localhost:30000/v1/chat/completions")
    monkeypatch.setenv("PE_MODEL", "served-model")
    monkeypatch.setenv("PE_API_KEY", "test-api-key")
    monkeypatch.setenv("PE_API_TIMEOUT", "120")
    monkeypatch.setenv("PE_API_RETRIES", "0")
    enhancer = OnlinePromptEnhancer(output_dir=tmp_path)
    assert enhancer.client.configured
    assert enhancer.client.api_url == "http://localhost:30000/v1/chat/completions"
    assert enhancer.client.model == "served-model"
    assert enhancer.client.api_key == "test-api-key"
    assert enhancer.client.timeout == 120
    assert enhancer.client.retries == 0


def test_environment_configures_server_reasoning_efforts():
    environment = dict(
        os.environ,
        PE_REASONING_EFFORTS="low,medium,xhigh",
        PE_DEFAULT_REASONING_EFFORT="medium",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from apps.kimi_k3_prompt_enhancer import "
            "KimiK3Client, PROMPT_ENHANCER_REASONING_EFFORTS; "
            "print(json.dumps([PROMPT_ENHANCER_REASONING_EFFORTS, "
            "KimiK3Client().request_payload([])['reasoning_effort']]))",
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == [["low", "medium", "xhigh"], "medium"]


def test_single_advertised_model_is_still_an_option(tmp_path):
    session = make_session()
    enhancer = OnlinePromptEnhancer(output_dir=tmp_path, client=KimiK3Client(session=session))
    assert [option["id"] for option in enhancer.model_options] == ["kimi-k3"]
    assert enhancer.default_model == "kimi-k3"
    assert enhancer.configured_for("kimi-k3")
    assert not enhancer.configured_for("removed-model")
    with pytest.raises(PromptEnhancementError, match="not advertised"):
        enhancer.client_for("removed-model")
    assert session.get.call_count == 1
    assert session.post.call_count == 0


@pytest.mark.parametrize("address,base", [
    ("http://localhost:30000", "http://localhost:30000/v1"),
    ("http://localhost:30000/v1/", "http://localhost:30000/v1"),
    ("https://localhost/proxy/30000/v1/chat/completions", "https://localhost/proxy/30000/v1"),
    ("https://localhost/proxy/30000", "https://localhost/proxy/30000/v1"),
])
@pytest.mark.parametrize("api_key", [None, "test-token"])
def test_discovery_uses_standard_url_and_auth(address, base, api_key):
    session = make_session()
    client = KimiK3Client(api_url=address, api_key=api_key, session=session)
    assert client.available_models() == ["kimi-k3"]
    assert client.api_url == base + "/chat/completions"
    assert session.get.call_args.args == (base + "/models",)
    assert session.get.call_args.kwargs["headers"].get("Authorization") == (
        f"Bearer {api_key}" if api_key else None
    )
    assert session.get.call_args.kwargs["timeout"] == (3, 5)


def test_discovery_deduplicates_ids_and_selects_advertised_default(tmp_path):
    session = make_session()
    session.get.return_value.json.return_value = {"data": [
        {"id": "org/Model-A"}, {"id": "kimi-k3"}, {"id": "org/Model-A"},
        {}, {"id": None}, {"id": ""}, {"id": " padded "}, "invalid",
    ]}
    enhancer = OnlinePromptEnhancer(
        output_dir=tmp_path, client=KimiK3Client(model="missing", session=session),
    )
    assert [option["id"] for option in enhancer.model_options] == ["org/Model-A", "kimi-k3"]
    assert enhancer.default_model == "org/Model-A"
    assert enhancer.resolve_model() == "org/Model-A"
    enhancer.client.model = "kimi-k3"
    assert enhancer.default_model == "kimi-k3"
    assert normalize_prompt_enhancer_model("org/Model-A") == "org/Model-A"
    assert session.get.call_count == 1


@pytest.mark.parametrize("failure", [
    requests.ConnectionError("offline"),
    requests.HTTPError("401 Unauthorized"),
    {"unexpected": []},
    {"data": []},
])
def test_failed_discovery_does_not_invent_models_and_recovers(tmp_path, failure):
    session = make_session()
    response = session.get.return_value
    if isinstance(failure, Exception):
        session.get.side_effect = failure
    else:
        response.json.return_value = failure
    client = KimiK3Client(session=session)
    enhancer = OnlinePromptEnhancer(output_dir=tmp_path, client=client)
    assert not enhancer.configured
    assert enhancer.model_options == []
    assert enhancer.default_model == ""
    with pytest.raises(PromptEnhancementError):
        enhancer.client_for("kimi-k3")
    assert session.get.call_count == 1
    assert session.post.call_count == 0
    session.get.side_effect = None
    response.json.return_value = {"data": [{"id": "RecoveredModel"}]}
    client._models_refresh_at = 0
    assert enhancer.configured
    assert enhancer.default_model == "RecoveredModel"
    assert client.models_error is None


def test_model_selection_is_request_local_and_audited(tmp_path):
    session = make_session()
    session.get.return_value.json.return_value = {"data": [
        {"id": "kimi-k3"}, {"id": "org/Model-A"},
    ]}
    client = KimiK3Client(session=session)
    enhancer = OnlinePromptEnhancer(output_dir=tmp_path, client=client)

    def selected_request(model):
        selected = enhancer.client_for(model)
        snapshot = _enhancer_request_snapshot(
            selected, [], reasoning_effort="low", seed=42,
        )
        assert selected.complete([], reasoning_effort="low", seed=42)[0] == "OK"
        return snapshot["model"]

    models = ["kimi-k3", "org/Model-A"] * 10
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(selected_request, models)) == models
    assert client.model == DEFAULT_PROMPT_ENHANCER_MODEL
    assert sorted(call.kwargs["json"]["model"] for call in session.post.call_args_list) == sorted(models)
    assert all(call.kwargs["json"]["reasoning_effort"] == "low"
               and call.kwargs["json"]["seed"] == 42 for call in session.post.call_args_list)


def test_multimodal_messages_pass_through():
    session = make_session(streaming=True)
    client = KimiK3Client(session=session)
    messages = [
        {"role": "system", "content": "Return segment JSON."},
        {"role": "assistant", "content": '{"segments":[]}'},
        {"role": "user", "content": [
            {"type": "text", "text": "video_timestamp: 00:02.000"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,test"}},
        ]},
    ]
    client.complete(messages)
    assert session.post.call_args.kwargs["json"]["messages"] == messages


def test_audit_snapshot_has_no_auth_or_internal_routing():
    client = KimiK3Client(api_key="secret-token")
    snapshot = _enhancer_request_snapshot(
        client, [], reasoning_effort="high", seed=42,
    )
    assert snapshot["model"] == DEFAULT_PROMPT_ENHANCER_MODEL
    assert snapshot["seed"] == 42
    assert "secret-token" not in json.dumps(snapshot)
    assert set(snapshot) == {
        "model", "messages", "reasoning_effort", "max_tokens", "stream",
        "seed", "api_url", "timeout",
    }


def test_nonretryable_error_fails_immediately():
    session = make_session()
    session.post.return_value.status_code = 401
    session.post.return_value.text = "Unauthorized"
    with pytest.raises(PromptEnhancementError, match="HTTP 401"):
        KimiK3Client(session=session).complete([])
    assert session.post.call_count == 1


def test_transient_network_failure_retries(monkeypatch):
    monkeypatch.setattr("apps.kimi_k3_prompt_enhancer.time.sleep", lambda _: None)
    session = make_session()
    response = session.post.return_value
    session.post.side_effect = [requests.ConnectionError("temporary"), response]
    assert KimiK3Client(session=session, retries=1).complete([]) == (
        "OK", "chatcmpl-test",
    )
    assert session.post.call_count == 2


def test_first_and_followup_preserve_timeline_history_and_branch(tmp_path, monkeypatch):
    session = make_session()
    client = KimiK3Client(session=session)
    enhancer = OnlinePromptEnhancer(output_dir=tmp_path, client=client)
    segment = {
        "start_time": "00:00.000",
        "end_time": "00:05.000",
        "visual_description_long": "A quiet park path.",
        "description_change": None,
        "contained_actions": [],
    }
    session.post.return_value.json.return_value = {
        "id": "first-request",
        "choices": [{"message": {"content": json.dumps({
            "perspective_view": "third-person follow",
            "Style": "real-world footage",
            "subject_list": [{
                "subject_id": "<|Subject1|>",
                "display_name": "cyclist",
                "subject_attribute": "A cyclist in a red jacket.",
            }],
            "segments": [segment],
        })}}],
    }
    first = enhancer.enhance({
        "session_id": "test-session",
        "perspective": "third-person follow",
        "style": "real-world footage",
        "subject": "A cyclist in a red jacket.",
        "action": "Ride along the path.",
        "camera_duration_ms": 5000,
    }, None, seed=42)
    assert first.num_frames == 120
    assert first.session["branch_revision"] == 0
    first.session["branch_revision"] = 2
    images = [("data:image/png;base64,test", 2.0, 2.0)]
    monkeypatch.setattr(
        enhancer, "_sample_previous_video_history", lambda *_: [images],
    )
    session.post.return_value.json.return_value = {
        "id": "followup-request",
        "choices": [{"message": {"content": json.dumps({
            "segments": [{
                **segment,
                "start_time": "00:05.000",
                "end_time": "00:07.000",
                "visual_description_long": None,
                "description_change": "Compared to the previous segment, the path curves.",
            }],
        })}}],
    }
    followup = enhancer.enhance({
        "session_id": "test-session",
        "action": "Continue riding.",
        "camera_duration_ms": 2000,
    }, first.session, seed=42)
    assert followup.num_frames == 48
    assert followup.session["branch_revision"] == 2
    assert followup.session["segment_frame_lengths"] == [120, 48]
    messages = session.post.call_args.kwargs["json"]["messages"]
    image_parts = [
        part
        for message in messages
        for part in (message["content"] if isinstance(message["content"], list) else [])
        if part.get("type") == "image_url"
    ]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"] == images[0][0]
