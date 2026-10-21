#!/bin/bash
# Source from the repository root to resolve YAML defaults and launch overrides.
export PYTHONPATH="${PWD}${PYTHONPATH:+:${PYTHONPATH}}"
_demo_config="$(python apps/seg_ar_demo_config.py "$@")"
eval "${_demo_config}"
unset _demo_config
