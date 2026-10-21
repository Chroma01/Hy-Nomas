# Recorded demo replay

This is a headless entry into `GenerationService`, not the merged offline
benchmark pipeline. It uses the archived, model-ready `prompts` and inline
`camera_trajectory` without parsing/shaping them again. Each original turn is
one collective call, with its original seed, local pixel boundaries, frame
count, guidance, solver, reset flag and persistent KV state.

## Build the manifest (CPU)

```bash
python scripts/inference/build_demo_replay_manifest.py \
  --input /path/to/camera.json \
  --output /path/to/camera_demo_replay.json
```

The builder reads each `source_attempt_path`, then the archived
`artifacts.metadata_path`. It embeds all required parameters in the manifest,
so the replay job does not need the original archives. Missing metadata,
partial sessions, and non-append retry/rollback history are rejected.

## Run with the matching deployment settings

```bash
bash scripts/inference/inference_from_config.sh \
  inference \
  --demo-replay /path/to/camera_demo_replay.json \
  dit_weight=/path/to/the-original-demo-checkpoint.safetensors \
  inference.save_path=/path/to/new-replay-output \
  parallelism.sp_size=8 \
  inference.seg_ar_segment_vae_decode=true \
  model.vae.stable_prefix_streaming=true \
  model.vae.name=pixelumm \
  model.vae.checkpoint=/path/to/the-original-pixelumm-checkpoint.safetensors
```

The DiT and PixelUMM checkpoints, normalization flags, SP size, and other relevant
settings must match the historical deployment. The public preset alone does
not establish that. Segment decoding is required for this replay path.

Run the same command on each allocated node. Existing launcher
topology logic is reused. Independent SP groups receive disjoint **sessions**,
never individual turns. Each torchrun world must contain exactly one SP replica.
Use a new output directory for each run: replay does not resume a session from
an empty KV cache or skip turns using the offline `skip_existing` logic.

Outputs are per-turn demo MP4s (including provisional-tail replacements), their
metadata, a `replay_group_NNN.jsonl` result journal, and the current resolved
`replay_config_group_NNN.yaml`. This is not a final cumulative stitched MP4;
replay intentionally uses the existing demo backend output semantics.

## What is and is not verified

The archived model inputs and per-turn request schedule are preserved. Camera
conversion, sampling, normalization, scale application, noise-bank behavior,
KV handling, and PixelUMM streaming run through the **current demo code path**.

The supplied historical metadata does **not** identify the original DiT/PixelUMM/
text-encoder weights, complete configuration (including displacement
normalization scope), code revision, SP topology, or runtime versions.
Accordingly the manifest explicitly records `historical_runtime_verified=false`.
This tool cannot certify bit-exact reproduction of historical videos without
those artifacts and an actual tensor/frame comparison. CPU tests verify replay
parameter preservation and history validation, not GPU numerical equivalence.

Setting `NOMAS_INFER_SAVE_LATENTS_DIR` enables the existing demo backend's
latent-output/hash capture for subsequent comparisons. Use identical settings
and compare decoded frames/latent tensors, not MP4 file hashes (encoding and
container metadata may differ).
