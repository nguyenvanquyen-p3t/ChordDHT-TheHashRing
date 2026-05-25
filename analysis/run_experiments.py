import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "analysis" / "results" / "hop_results.csv"
DEFAULT_CHART = ROOT_DIR / "chord_analysis_chart.png"


def parse_node_counts(raw):
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def run_command(command):
    command = [str(part) for part in command]
    print(" ".join(command))
    subprocess.run(command, cwd=ROOT_DIR, check=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Run Chord experiments for multiple N values.")
    parser.add_argument("--node-counts", default="10,20,30,40,50")
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chart", type=Path, default=DEFAULT_CHART)
    parser.add_argument("--wait-seconds", type=int, default=25)
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Only run simulate_queries.py; assumes the requested network is already running.",
    )
    parser.add_argument("--insert-resources", action="store_true")
    parser.add_argument("--verify-gets", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    node_counts = parse_node_counts(args.node_counts)

    if args.output.exists():
        args.output.unlink()

    for node_count in node_counts:
        if not args.skip_docker:
            run_command([sys.executable, "scripts/generate_compose.py", "--nodes", node_count])
            run_command(["docker", "compose", "down", "--remove-orphans"])
            run_command(["docker", "compose", "up", "-d", "--build"])
            print(f"Waiting {args.wait_seconds}s for stabilization...")
            time.sleep(args.wait_seconds)

        simulate_command = [
            sys.executable,
            "analysis/simulate_queries.py",
            "--queries",
            args.queries,
            "--seed",
            args.seed,
            "--node-count",
            node_count,
            "--output",
            args.output,
            "--chart",
            args.chart,
            "--append",
        ]
        if args.insert_resources:
            simulate_command.append("--insert-resources")
        if args.verify_gets:
            simulate_command.extend(["--verify-gets", args.verify_gets])

        try:
            run_command(simulate_command)
        finally:
            if not args.skip_docker:
                run_command(["docker", "compose", "down"])

    if not args.skip_docker:
        run_command([sys.executable, "scripts/generate_compose.py", "--nodes", node_counts[-1]])

    print(f"Experiment CSV: {args.output}")
    print(f"Experiment chart: {args.chart}")


if __name__ == "__main__":
    main()
