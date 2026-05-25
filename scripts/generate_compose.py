import argparse
from pathlib import Path

import yaml

DEFAULT_NODES = 50
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "docker-compose.yml"


def build_compose_dict(num_nodes):
    if num_nodes < 1:
        raise ValueError("--nodes must be at least 1")

    compose_dict = {
        "version": "3.8",
        "services": {},
        "networks": {"chord_net": {"driver": "bridge"}},
    }

    compose_dict["services"]["node-0"] = {
        "build": ".",
        "container_name": "chord-node-0",
        "hostname": "node-0",
        "networks": ["chord_net"],
        "environment": ["IS_SEED=True", "PYTHONUNBUFFERED=1"],
        "ports": ["5000:5000"],
    }

    for i in range(1, num_nodes):
        node_name = f"node-{i}"
        service = {
            "build": ".",
            "container_name": f"chord-node-{i}",
            "hostname": node_name,
            "networks": ["chord_net"],
            "depends_on": ["node-0"],
            "environment": [
                "IS_SEED=False",
                "KNOWN_NODE=node-0",
                "PYTHONUNBUFFERED=1",
            ],
        }
        if i <= 5:
            service["ports"] = [f"{5000 + i}:5000"]
        compose_dict["services"][node_name] = service

    return compose_dict


def write_compose(num_nodes, output_path):
    compose_dict = build_compose_dict(num_nodes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(compose_dict, f, default_flow_style=False, sort_keys=False)
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(description="Generate docker-compose.yml for Chord nodes.")
    parser.add_argument("--nodes", type=int, default=DEFAULT_NODES, help="Number of Chord nodes.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write the docker-compose file.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = write_compose(args.nodes, args.output)
    print(f"Generated {output_path} for {args.nodes} Chord nodes.")


if __name__ == "__main__":
    main()
