import argparse
import csv
import math
import random
import sys
import time
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.utils.hashing import build_resource_record  # noqa: E402

DEFAULT_OUTPUT = ROOT_DIR / "analysis" / "results" / "hop_results.csv"
DEFAULT_CHART = ROOT_DIR / "chord_analysis_chart.png"


def generate_resource_dataset(count):
    return [build_resource_record(f"resource_{idx:04d}") for idx in range(1, count + 1)]


def _write_csv_row(path, row, append=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not append or not path.exists()
    mode = "a" if append else "w"
    with path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _write_details(path, rows):
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "query_index",
        "resource_key",
        "ring_id",
        "status",
        "hops",
        "owner_id",
        "owner_ip",
        "source",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _plot_results(summary_csv, chart_path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipping chart generation.")
        return

    rows = []
    with summary_csv.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    if not rows:
        return

    rows.sort(key=lambda item: int(item["node_count"]))
    n_values = [int(row["node_count"]) for row in rows]
    avg_hops = [float(row["avg_hops"]) for row in rows]
    theoretical = [float(row["theoretical_log2_half"]) for row in rows]

    plt.figure(figsize=(8, 5))
    plt.plot(n_values, avg_hops, marker="o", label="Measured average hops")
    plt.plot(n_values, theoretical, marker="x", linestyle="--", label="0.5 * log2(N)")
    plt.title("Chord DHT lookup hops vs node count")
    plt.xlabel("Number of nodes (N)")
    plt.ylabel("Average hops")
    plt.xticks(n_values)
    plt.grid(True)
    plt.legend()
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(chart_path, bbox_inches="tight")
    plt.close()


def _lookup(base_url, resource):
    resp = requests.get(
        f"{base_url}/find_successor",
        params={"id": resource["ring_id"]},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()


def _insert(base_url, resource):
    resp = requests.post(
        f"{base_url}/resources",
        json={"resource_key": resource["resource_key"], "value": resource["value"]},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()


def _get_resource(base_url, resource_key):
    resp = requests.get(f"{base_url}/resources/{resource_key}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def run_simulation(args):
    dataset = generate_resource_dataset(args.queries)
    random.Random(args.seed).shuffle(dataset)

    total_hops = 0
    max_hops = 0
    successes = 0
    failures = 0
    detail_rows = []
    started_at = time.perf_counter()

    print(
        f"Running {args.queries} {'insert' if args.insert_resources else 'lookup'} "
        f"queries against {args.base_url} for N={args.node_count}"
    )

    for idx, resource in enumerate(dataset, start=1):
        try:
            result = _insert(args.base_url, resource) if args.insert_resources else _lookup(args.base_url, resource)
            hops = int(result.get("hops", 0))
            owner_id = result.get("node_id") or result.get("owner", {}).get("node_id")
            owner_ip = result.get("node_ip") or result.get("owner", {}).get("node_ip")
            source = result.get("source", "lookup")

            total_hops += hops
            max_hops = max(max_hops, hops)
            successes += 1
            detail_rows.append(
                {
                    "query_index": idx,
                    "resource_key": resource["resource_key"],
                    "ring_id": resource["ring_id"],
                    "status": "ok",
                    "hops": hops,
                    "owner_id": owner_id,
                    "owner_ip": owner_ip,
                    "source": source,
                    "error": "",
                }
            )
        except Exception as exc:
            failures += 1
            detail_rows.append(
                {
                    "query_index": idx,
                    "resource_key": resource["resource_key"],
                    "ring_id": resource["ring_id"],
                    "status": "error",
                    "hops": "",
                    "owner_id": "",
                    "owner_ip": "",
                    "source": "",
                    "error": str(exc),
                }
            )

        if args.progress_every and idx % args.progress_every == 0:
            print(f"Completed {idx}/{args.queries} queries")

    verify_successes = 0
    if args.insert_resources and args.verify_gets:
        for resource in dataset[: args.verify_gets]:
            try:
                result = _get_resource(args.base_url, resource["resource_key"])
                if result.get("found") and result.get("value") == resource["value"]:
                    verify_successes += 1
            except Exception:
                pass

    elapsed_seconds = time.perf_counter() - started_at
    avg_hops = total_hops / successes if successes else 0.0
    theoretical = math.log2(args.node_count) / 2 if args.node_count > 1 else 0.0
    summary = {
        "node_count": args.node_count,
        "queries": args.queries,
        "seed": args.seed,
        "mode": "insert" if args.insert_resources else "lookup",
        "successes": successes,
        "failures": failures,
        "avg_hops": f"{avg_hops:.4f}",
        "max_hops": max_hops,
        "theoretical_log2_half": f"{theoretical:.4f}",
        "verify_gets": args.verify_gets,
        "verify_successes": verify_successes,
        "elapsed_seconds": f"{elapsed_seconds:.2f}",
    }

    _write_csv_row(args.output, summary, append=args.append)
    _write_details(args.details_output, detail_rows)
    if args.chart:
        _plot_results(args.output, args.chart)

    print("-" * 40)
    print(f"N={args.node_count}, successes={successes}, failures={failures}")
    print(f"Average hops={avg_hops:.2f}, max hops={max_hops}")
    print(f"Theory reference 0.5*log2(N)={theoretical:.2f}")
    print(f"Summary CSV: {args.output}")
    if args.chart:
        print(f"Chart: {args.chart}")
    print("-" * 40)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="Run Chord lookup/resource simulations.")
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--node-count", type=int, default=50)
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--details-output", type=Path)
    parser.add_argument("--chart", type=Path, default=DEFAULT_CHART)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--insert-resources", action="store_true")
    parser.add_argument("--verify-gets", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    run_simulation(parse_args())
