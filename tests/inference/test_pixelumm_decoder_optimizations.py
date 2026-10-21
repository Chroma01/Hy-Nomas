"""Opt-in PixelUMM decoder inference optimizations: default-off contract and GPU parity.

The default path must not need DeepGEMM, CUTLASS or the CuTe DSL, so it is asserted on CPU.
The CUDA tests compare each optimization with the unmodified decoder and skip without the
matching hardware and package.

``maybe_load_pixelumm_decoder`` builds the full Qwen3-8B decoder, so the default-off contract is
asserted on ``_install_inference_optimizations`` (the function the loader calls) instead of
building 8B weights on CPU.
"""

from __future__ import annotations

import copy
import importlib.util
import os
import sys
from types import SimpleNamespace

import pytest
import torch

from hymm.models.vae.pixelumm_decoder import maybe_load_pixelumm_decoder
from hymm.models.vae.pixelumm_decoder.loader import _install_inference_optimizations
from hymm.models.vae.pixelumm_decoder.model import (
    DCAEVPixelUMMDecoder,
    GenExpertArch,
    local_attention_layout,
    mrope_tables,
)

TINY = GenExpertArch(
    hidden_size=64, intermediate_size=128, num_layers=2, num_heads=4, num_kv_heads=2, head_dim=16
)
OPTIONAL_MODULES = ("deep_gemm", "cutlass", "cuda.bindings")
SWITCHES = ("deepgemm_fp8", "cutlass_fp8", "cute_attention", "compile_decoder")


def _decoder() -> DCAEVPixelUMMDecoder:
    torch.manual_seed(1234)
    return DCAEVPixelUMMDecoder(TINY).eval().requires_grad_(False)


def _quiet_logger() -> SimpleNamespace:
    return SimpleNamespace(info=lambda *_: None)


def _modules_loaded() -> set:
    return {name for name in OPTIONAL_MODULES if name in sys.modules}


def test_default_config_installs_nothing_and_imports_nothing_extra():
    decoder = _decoder()
    before_modules, before_params = _modules_loaded(), set(decoder.state_dict())
    _install_inference_optimizations(decoder, SimpleNamespace(), _quiet_logger())
    assert _modules_loaded() == before_modules
    assert set(decoder.state_dict()) == before_params  # no FP8 buffers appeared
    assert "forward" not in decoder.__dict__  # not compiled
    for layer in decoder.layers:
        assert type(layer.mlp.gate_proj) is torch.nn.Linear
        assert "forward" not in layer.attn.__dict__  # CuTe not installed


def test_explicitly_false_switches_behave_like_absent_ones():
    decoder = _decoder()
    before_modules = _modules_loaded()
    config = SimpleNamespace(**{name: False for name in SWITCHES})
    _install_inference_optimizations(decoder, config, _quiet_logger())
    assert "forward" not in decoder.__dict__
    assert _modules_loaded() == before_modules


def test_compile_switch_wraps_the_decoder_forward(monkeypatch):
    calls = []
    monkeypatch.setattr(torch, "compile", lambda fn, **kwargs: calls.append(kwargs) or fn)
    decoder = _decoder()
    before_params = set(decoder.state_dict())
    _install_inference_optimizations(decoder, SimpleNamespace(compile_decoder=True), _quiet_logger())
    assert calls == [{"mode": "default", "fullgraph": True, "dynamic": False}]
    assert set(decoder.state_dict()) == before_params


def test_two_fp8_backends_are_rejected_before_the_checkpoint_is_read():
    args = SimpleNamespace(
        vae=SimpleNamespace(
            name="pixelumm",
            checkpoint="/nonexistent.safetensors",
            deepgemm_fp8=True,
            cutlass_fp8=True,
        ),
        inference=SimpleNamespace(),
    )
    with pytest.raises(ValueError, match="only one FP8 backend"):
        maybe_load_pixelumm_decoder(args, device=torch.device("cpu"), logger=_quiet_logger())


def _capability():
    return torch.cuda.get_device_capability() if torch.cuda.is_available() else None


cuda = pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")


@cuda
@pytest.mark.parametrize("cute", [False, True])
def test_sliding_tile_decoder_compiles_fullgraph_and_matches_eager(cute):
    if cute and (_capability() != (9, 0) or importlib.util.find_spec("cutlass") is None):
        pytest.skip("CuTe needs SM90 and nvidia-cutlass-dsl")
    torch.manual_seed(42)
    arch = GenExpertArch(
        hidden_size=256, intermediate_size=512, num_layers=1, num_heads=4, num_kv_heads=2, head_dim=128
    )
    reference = DCAEVPixelUMMDecoder(arch, local_attention_tile=2).cuda().bfloat16().eval().requires_grad_(False)
    candidate = copy.deepcopy(reference)
    if cute:
        from hymm.models.vae.pixelumm_decoder.cute_attention import enable_cute_attention

        enable_cute_attention(candidate)
    latent = torch.randn(1, 32, 2, 4, 4, device="cuda", dtype=torch.bfloat16)
    xt = torch.randn(reference.pixel_shape(latent), device="cuda", dtype=torch.bfloat16)
    local_attention_layout((2, 8, 8), 2, latent.device)  # built outside the compiled region
    with torch.no_grad():
        expected = reference(latent, xt)
        compiled = torch.compile(candidate.forward, fullgraph=True, dynamic=False)
        actual = compiled(latent, xt)
        torch.testing.assert_close(actual, expected, atol=0.04, rtol=0.04)
        torch.testing.assert_close(compiled(latent, xt), actual, atol=0, rtol=0)
    # This tiny shape deliberately falls below the CuTe occupancy floor.
    if cute:
        from hymm.models.vae.pixelumm_decoder.cute_attention import execution_stats

        assert execution_stats().get("qkv_prepare", 0) in (0, 1)


@cuda
@pytest.mark.parametrize("grid", [(2, 16, 16), (1, 9, 17)])
def test_cute_sliding_tile_keeps_mask_and_unexpanded_kv(grid):
    if _capability() != (9, 0) or importlib.util.find_spec("cutlass") is None:
        pytest.skip("CuTe needs SM90 and nvidia-cutlass-dsl")
    from hymm.models.vae.pixelumm_decoder.cute_attention import enable_cute_attention, execution_stats

    torch.manual_seed(43)
    arch = GenExpertArch(
        hidden_size=256, intermediate_size=512, num_layers=1, num_heads=4, num_kv_heads=2, head_dim=128
    )
    model = DCAEVPixelUMMDecoder(arch, local_attention_tile=2).cuda().bfloat16().eval().requires_grad_(False)
    original = model.layers[0].attn.forward
    enable_cute_attention(model)
    perm, _, mask = local_attention_layout(grid, 2, "cuda:0")
    x = torch.randn(2, perm.numel(), 256, device="cuda", dtype=torch.bfloat16)
    cos, sin = mrope_tables(arch, grid, x.device)
    cos, sin = cos[:, perm], sin[:, perm]
    with torch.no_grad():
        reference = original(x, cos, sin, mask)
        before = execution_stats().get("qkv_prepare", 0)
        actual = model.layers[0].attn(x, cos, sin, mask)
        assert execution_stats()["qkv_prepare"] == before + 1
        relative = (actual.float() - reference.float()).norm() / reference.float().norm()
        assert relative < 0.003, relative


def test_fp8_linear_keeps_quantized_buffer_dtypes_across_module_dtype_cast(monkeypatch):
    """``vae.to(device, dtype=bf16)`` (done between segments) must not cast fp8 buffers to bf16."""
    stub = SimpleNamespace(
        utils=SimpleNamespace(
            per_block_cast_to_fp8=lambda w, use_ue8m0: (w.to(torch.float8_e4m3fn), torch.ones(w.shape[0], 1))
        )
    )
    monkeypatch.setitem(sys.modules, "deep_gemm", stub)
    from hymm.models.vae.pixelumm_decoder.fp8 import FP8Linear

    layer = FP8Linear(torch.nn.Linear(128, 128, bias=False))
    layer.to(device="cpu", dtype=torch.bfloat16)
    assert layer.fp8_weight.dtype == torch.float8_e4m3fn
    assert layer.fp8_scale.dtype == torch.float32
    assert layer.weight.dtype == torch.bfloat16
    assert "fp8_weight" in dict(layer.named_buffers())


@cuda
def test_deepgemm_fp8_linear_matches_bf16_within_quantization_error():
    if _capability() != (9, 0) or importlib.util.find_spec("deep_gemm") is None:
        pytest.skip("DeepGEMM needs SM90 and the deep_gemm package")
    from hymm.models.vae.pixelumm_decoder.fp8 import FP8Linear

    torch.manual_seed(46)
    reference = torch.nn.Linear(256, 512, bias=False, device="cuda", dtype=torch.bfloat16).eval()
    layer = FP8Linear(reference)
    x = torch.randn(2, 129, 256, device="cuda", dtype=torch.bfloat16)
    with torch.no_grad():
        eager = layer(x)
        compiled = torch.compile(layer, fullgraph=True, dynamic=False)
        torch.testing.assert_close(compiled(x), eager, atol=0, rtol=0)
        assert (eager.float() - reference(x).float()).norm() / reference(x).float().norm() < 0.06
    layer.train()
    with pytest.raises(RuntimeError, match="inference"):
        layer(x)


@cuda
@pytest.mark.parametrize("m,n,k", [(1, 128, 128), (129, 256, 384), (2560, 4096, 4096), (4097, 128, 4096)])
def test_cutlass_blockwise_gemm_matches_dequantized_reference(m, n, k):
    if _capability() != (8, 9) or not os.environ.get("CUTLASS_PATH"):
        pytest.skip("CUTLASS FP8 needs SM89 and CUTLASS_PATH")
    from hymm.models.vae.pixelumm_decoder.cutlass_fp8 import _quantize_blockwise, load_extension

    def dequant(q, s):
        return q.float() * s.repeat_interleave(128, 0).repeat_interleave(128, 1)[: q.shape[0]]

    torch.manual_seed(44)
    a = torch.randn(m, k, device="cuda", dtype=torch.bfloat16)
    b = torch.randn(n, k, device="cuda", dtype=torch.bfloat16)
    a[:, 128:256] *= 20  # distinct per-K-block scales catch epilogue-only scaling
    b[:128] *= 0.03
    qa, sa = _quantize_blockwise(a)
    qb, sb = _quantize_blockwise(b)
    with torch.no_grad():
        actual = load_extension().gemm(qa, qb, sa, sb)
    expected = dequant(qa, sa) @ dequant(qb, sb).T
    assert (actual.float() - expected).norm() / expected.norm() < 0.004
    assert torch.isfinite(actual).all()
