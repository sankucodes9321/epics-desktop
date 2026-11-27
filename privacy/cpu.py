import os
from functools import cache
from pathlib import Path


def defaults():
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    if os.getenv("ZKAUTH_FORCE_CPU", "1") != "0":
        for name, value in {"CUDA_VISIBLE_DEVICES": "-1", "TF_CPP_MIN_LOG_LEVEL": "2",
                            "TF_ENABLE_ONEDNN_OPTS": "1"}.items():
            os.environ.setdefault(name, value)


def cpu_info():
    blocks = Path("/proc/cpuinfo").read_text().strip().split("\n\n")
    rows = [dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
            for block in blocks]
    rows = [{k.strip(): v.strip() for k, v in row.items()} for row in rows]
    pairs = {(r["physical id"], r["core id"]) for r in rows if "core id" in r and "physical id" in r}
    return rows[0].get("model name", "unknown"), len(pairs) or len(rows)


def force_cpu():
    from .errors import PipelineError
    value = os.getenv("ZKAUTH_FORCE_CPU", "1")
    if value not in ("0", "1"):
        raise PipelineError("ZKAUTH_FORCE_CPU must be 0 or 1.")
    return value == "1"


@cache
def threads(antispoof):
    from .config import number
    count = number("ZKAUTH_CPU_THREADS", cpu_info()[1], 1)
    cpu_only = force_cpu()
    if antispoof:
        import torch
        if cpu_only and torch.cuda.is_available():
            from .errors import PipelineError
            raise PipelineError("GPU visible in CPU mode. Set CUDA_VISIBLE_DEVICES=-1 and restart.")
        torch.set_num_threads(count)
    import tensorflow as tf
    if cpu_only:
        tf.config.set_visible_devices([], "GPU")
    tf.config.threading.set_intra_op_parallelism_threads(count)
    tf.config.threading.set_inter_op_parallelism_threads(1)
