"""Model IDs and explicit checkpoint paths work without a shared assets root."""

from argparse import Namespace
from unittest.mock import Mock

import pytest
import torch

from apps.seg_ar_demo_config import (
    apply_server_overrides, launcher_overrides, load_demo_config,
)
from hymm.models.checkpointing import load
from hymm.models.text_encoder import encoder
from hymm.models.vae import load_vae


@pytest.mark.parametrize("local_path", [None, "/tmp/local qwen"])
def test_text_encoder_and_tokenizer_receive_exact_model_source(monkeypatch, local_path):
    overrides = [] if local_path is None else [f'model.text_encoder.model_name="{local_path}"']
    config = load_demo_config(overrides)
    source = local_path or "Qwen/Qwen2.5-VL-7B-Instruct"
    model = Mock(dtype=torch.bfloat16, device=torch.device("cpu"))
    model.language_model = Mock(dtype=torch.bfloat16, device=torch.device("cpu"))
    model.language_model.to.return_value = model.language_model
    model_factory = Mock(return_value=model)
    tokenizer_factory = Mock()
    monkeypatch.setattr(encoder.AutoModel, "from_pretrained", model_factory)
    monkeypatch.setattr(encoder.AutoTokenizer, "from_pretrained", tokenizer_factory)
    # Template tokenization is independent of asset resolution.
    config.text_encoder.prompt_template = None
    config.text_encoder.prompt_template_video = None
    primary = load.load_text_encoder(torch.device("cpu"), Mock(), config)
    model_factory.assert_called_once_with(source, low_cpu_mem_usage=True)
    tokenizer_factory.assert_called_once_with(source, padding_side="right")
    assert primary.model_path == source
    assert primary.tokenizer_path == source


def test_demo_local_path_override_survives_launch_and_server_flags():
    overrides = launcher_overrides([
        "--text-encoder-model", "/tmp/local qwen",
    ], {})
    config = load_demo_config(overrides)
    assert config.text_encoder.model_name == "/tmp/local qwen"
    assert "path" not in config.text_encoder
    apply_server_overrides(config, Namespace(
        dit_weight=None, text_encoder_model="/tmp/another qwen",
        rollout_type=None, output_dir=None, dry_run_source=None,
    ))
    assert config.text_encoder.model_name == "/tmp/another qwen"


def test_dcae_requires_explicit_checkpoint():
    with pytest.raises(ValueError, match="model.vae.checkpoint"):
        load_vae(device="cpu")


def test_dcae_loads_exact_checkpoint(monkeypatch):
    from hymm.models.vae.autoencoder_dcae_v import AutoencoderDCAEV

    factory = Mock()
    monkeypatch.setattr(AutoencoderDCAEV, "from_checkpoint", factory)
    model, path, _, _ = load_vae(vae_path="/tmp/custom-dcae.pt", device="cpu")
    factory.assert_called_once_with(
        checkpoint_path="/tmp/custom-dcae.pt", dtype=torch.bfloat16, device="cpu",
    )
    assert model is factory.return_value
    assert path == "/tmp/custom-dcae.pt"
