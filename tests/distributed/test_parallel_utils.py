#!/usr/bin/env python3
"""CPU/Gloo smoke test for the repository-local parallel helpers."""

from __future__ import annotations

import os
import random

import numpy as np
import torch
import torch.distributed as dist

from hymm.utils.parallel import (
    sync_object_for_parallel_training,
    sync_random_states,
)


class TestParallelDims:
    tp_enabled = False
    pp_enabled = False
    sp_enabled = True

    def __init__(self):
        self.sp_group = dist.group.WORLD


def main():
    dist.init_process_group("gloo")
    rank = dist.get_rank()
    dims = TestParallelDims()

    tensor = torch.tensor([rank + 1.0, rank + 2.0])
    synced_tensor = sync_object_for_parallel_training(tensor, parallel_dims=dims)
    assert torch.equal(synced_tensor, torch.tensor([1.0, 2.0]))

    nested = {
        "rank": rank,
        "values": [torch.tensor([rank]), (rank, "source" if rank == 0 else "other")],
        "labels": {"a", "b"} if rank == 0 else {"x"},
    }
    synced_nested = sync_object_for_parallel_training(nested, parallel_dims=dims)
    assert synced_nested["rank"] == 0
    assert torch.equal(synced_nested["values"][0], torch.tensor([0]))
    assert synced_nested["values"][1] == [0, "source"]
    assert synced_nested["labels"] == {"a", "b"}

    forced = sync_object_for_parallel_training(
        {"cursor": 17 + rank}, parallel_dims=dims, force_object=True
    )
    assert forced == {"cursor": 17}

    torch.manual_seed(100 + rank)
    np.random.seed(200 + rank)
    random.seed(300 + rank)
    sync_random_states(dims)
    values = (
        torch.rand(4).tolist(),
        np.random.rand(4).tolist(),
        [random.random() for _ in range(4)],
    )
    gathered = [None] * dist.get_world_size()
    dist.all_gather_object(gathered, values)
    assert all(value == gathered[0] for value in gathered)

    if rank == 0:
        print("PASS repository-local parallel helpers", flush=True)
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
