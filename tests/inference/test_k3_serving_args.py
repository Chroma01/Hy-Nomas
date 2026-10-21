import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "captioning_harness/serve_k3.sh"


def serving_args(**overrides):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("K3_") and key != "SGLANG_PP_LAYER_PARTITION"}
    env.update(K3_MODEL_PATH="/path/to/kimi-k3", K3_DIST_INIT_ADDR="node-zero:50000")
    env.update(overrides)
    # Replace the interpreter on PATH so the launcher can be checked without GPUs.
    command = (
        'function exec() { printf "partition=%s\\n" "${SGLANG_PP_LAYER_PARTITION:-}"; '
        'printf "%s\\n" "$@"; }; export -f exec; bash "$1"'
    )
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", command, "test", str(SCRIPT)],
        env=env, text=True, capture_output=True, check=True,
    ).stdout.splitlines()


def test_k3_serving_defaults_match_multiturn_captioning():
    args = serving_args()
    assert args[0] == "partition=24,23,23,23"
    expected = {
        "--nnodes": "4", "--tp-size": "8", "--pp-size": "4", "--ep-size": "8",
        "--mem-fraction-static": "0.90", "--context-length": "262144",
        "--max-running-requests": "144", "--cuda-graph-max-bs-decode": "64",
        "--mamba-full-memory-ratio": "1.1", "--chunked-prefill-size": "16384",
        "--pp-max-micro-batch-size": "32", "--pp-async-batch-depth": "8",
    }
    for flag, value in expected.items():
        assert args[args.index(flag) + 1] == value


def test_single_node_overrides_do_not_inherit_pipeline_options():
    args = serving_args(
        K3_NNODES="1", K3_PP_SIZE="1", K3_MEM_FRACTION_STATIC="0.8",
        K3_CONTEXT_LENGTH="32768", K3_EXTRA_ARGS="--max-running-requests 12",
    )
    assert args[0] == "partition="
    assert "--pp-max-micro-batch-size" not in args
    assert "--pp-async-batch-depth" not in args
    assert args[args.index("--context-length") + 1] == "32768"
    assert args[args.index("--mem-fraction-static") + 1] == "0.8"
    assert args[-2:] == ["--max-running-requests", "12"]
