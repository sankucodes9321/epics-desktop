"""Time live identification stages against configured encrypted references."""
import argparse
import json
import resource
import sys

import numpy as np

from main import warmup
from privacy.config import face_settings
from privacy.cpu import cpu_info, threads
from privacy.encryption import encrypt
from privacy.errors import PipelineError
from privacy.matching import Matcher, references, cosine
from privacy.runtime import startup
from privacy.timing import collect


def summarize(iterations, action):
    samples = {}
    for _ in range(iterations):
        with collect() as values:
            action()
        for stage, seconds in values.items():
            samples.setdefault(stage, []).append(seconds)
    return {stage: dict(mean=np.mean(times), median=np.median(times), p95=np.percentile(times, 95))
            for stage, times in samples.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--iterations", type=int, default=10)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("iterations must be positive")
    startup()
    matcher = Matcher.configured()
    settings = face_settings()
    threads(settings.antispoof)
    warmup(settings.detector, settings.antispoof)
    records = matcher.all_records()
    if not records:
        raise PipelineError("Enroll a reference before benchmarking.")

    def iteration():
        with matcher.probe() as vector, references(records, matcher.key) as matrix:
            encrypt(vector, matcher.key)
            cosine(matrix, vector)
    stages = summarize(args.iterations, iteration)
    model, cores = cpu_info()
    print(json.dumps(dict(seconds=stages, iterations=args.iterations, cpu=model, physical_cores=cores,
                          peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"Benchmark failed ({type(exc).__name__}).")
