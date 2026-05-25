from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.chord.node_logic import ChordNode, in_interval  # noqa: E402
from app.utils.hashing import MAX_NODES, build_resource_record, get_hash  # noqa: E402
from scripts.generate_compose import build_compose_dict  # noqa: E402


def test_in_interval_normal_and_wraparound():
    assert in_interval(15, 10, 20)
    assert not in_interval(10, 10, 20)
    assert in_interval(20, 10, 20, inclusive_end=True)
    assert in_interval(3, 60, 10)
    assert in_interval(61, 60, 10)
    assert not in_interval(30, 60, 10)
    assert in_interval(5, 5, 5)


def test_hash_is_stable_and_in_ring():
    first = get_hash("resource_0001")
    second = get_hash("resource_0001")
    assert first == second
    assert 0 <= first < MAX_NODES

    record = build_resource_record("resource_0001", "value")
    assert record["resource_key"] == "resource_0001"
    assert record["value"] == "value"
    assert 0 <= record["ring_id"] < MAX_NODES
    assert len(record["sha1_hex"]) == 40


def test_closest_preceding_node_selects_largest_safe_finger():
    node = ChordNode("test-node", "test-node")
    node.id = 10
    node.finger_table = [
        {"start": 11, "node_id": 12, "node_ip": "node-a"},
        {"start": 12, "node_id": 20, "node_ip": "node-b"},
        {"start": 14, "node_id": 40, "node_ip": "node-c"},
    ]

    result = node.closest_preceding_node(35)
    assert result == {"node_id": 20, "node_ip": "node-b"}


def test_generate_compose_uses_requested_node_count():
    compose_10 = build_compose_dict(10)
    assert len(compose_10["services"]) == 10
    assert compose_10["services"]["node-0"]["environment"][0] == "IS_SEED=True"
    assert compose_10["services"]["node-9"]["environment"][1] == "KNOWN_NODE=node-0"

    compose_50 = build_compose_dict(50)
    assert len(compose_50["services"]) == 50
    assert "node-49" in compose_50["services"]
