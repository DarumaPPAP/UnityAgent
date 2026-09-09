#!/usr/bin/env python3
"""Run retrieval evaluation against a checked-in frozen retrieval baseline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Retrieval.run_retrieval_eval import DEFAULT_BASELINE, DEFAULT_DATASET, DEFAULT_INDEX, run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()
    report = run(dataset_path=args.dataset, index_path=args.index, baseline_path=args.baseline)
    print(f"Retrieval regression decision: {report['decision']}")
    for failure in (report.get("failure_attribution") or {}).get("regression_failures", []):
        print(f"- {failure['metric']}: {failure['actual']} < baseline {failure['baseline']}")
    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
