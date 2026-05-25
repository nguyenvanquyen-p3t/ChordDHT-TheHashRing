import os
import time

import requests
from flask import Flask, jsonify, request

from app.chord.node_logic import ChordNode, clockwise_distance, in_interval
from app.chord.stabilize import start_background_tasks
from app.utils.hashing import M, MAX_NODES, build_resource_record

app = Flask(__name__)

NODE_NAME = os.environ.get("HOSTNAME", "node-unknown")
IS_SEED = os.environ.get("IS_SEED", "False") == "True"
KNOWN_NODE = os.environ.get("KNOWN_NODE")
PORT = 5000
REQUEST_TIMEOUT = 2
LOOKUP_MAX_HOPS = M * 2

my_node = ChordNode(node_name=NODE_NAME, ip_address=NODE_NAME, port=PORT)


def _url(node_ip, path):
    return f"http://{node_ip}:{PORT}{path}"


def _parse_path(raw_path):
    if not raw_path:
        return []

    path = []
    for item in raw_path.split(";"):
        if not item or "@" not in item:
            continue
        node_id, node_ip = item.split("@", 1)
        try:
            path.append({"node_id": int(node_id), "node_ip": node_ip})
        except ValueError:
            continue
    return path


def _encode_path(path):
    return ";".join(f"{node['node_id']}@{node['node_ip']}" for node in path)


def _parse_visited(raw_visited):
    if not raw_visited:
        return set()
    return {item for item in raw_visited.split(",") if item}


def _encode_visited(visited):
    return ",".join(sorted(visited))


def _append_current(path):
    current = my_node.descriptor()
    if not path or path[-1]["node_ip"] != current["node_ip"]:
        path.append(current)
    return path


def _path_with_owner(path, owner):
    result_path = list(path)
    if not result_path or result_path[-1]["node_ip"] != owner["node_ip"]:
        result_path.append(owner)
    return result_path


def _is_alive(node_ip):
    if node_ip == my_node.ip_address:
        return True
    try:
        resp = requests.get(_url(node_ip, "/health"), timeout=REQUEST_TIMEOUT)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _choose_live_replacement(excluded_ips=None):
    excluded_ips = excluded_ips or set()
    candidates = my_node.known_nodes(excluded_ips=excluded_ips)
    candidates.sort(key=lambda item: clockwise_distance(my_node.id, item["node_id"]))

    for candidate in candidates:
        candidate_ip = candidate["node_ip"]
        if candidate_ip in excluded_ips or candidate_ip == my_node.ip_address:
            continue
        if _is_alive(candidate_ip):
            return candidate
        my_node.remove_known_node(candidate_ip)

    return None


def _ensure_live_successor():
    successor_ip = my_node.successor_ip
    if successor_ip == my_node.ip_address or _is_alive(successor_ip):
        return True

    my_node.remove_known_node(successor_ip)
    replacement = _choose_live_replacement(excluded_ips={successor_ip})
    if replacement:
        my_node.set_successor(replacement["node_id"], replacement["node_ip"])
        return True

    my_node.set_successor(my_node.id, my_node.ip_address)
    return False


def _successor_result(target_id, hop_count, path, resolved_by):
    _ensure_live_successor()
    owner = {"node_id": my_node.successor_id, "node_ip": my_node.successor_ip}
    return {
        "target_id": target_id,
        "node_id": owner["node_id"],
        "node_ip": owner["node_ip"],
        "hops": hop_count,
        "path": _path_with_owner(path, owner),
        "resolved_by": resolved_by,
    }


def _candidate_nodes(target_id, visited):
    candidates = []
    closest = my_node.closest_preceding_node(target_id, excluded_ips=visited)
    if closest["node_ip"] != my_node.ip_address:
        candidates.append(closest)

    with my_node.lock:
        finger_candidates = [
            {"node_id": item["node_id"], "node_ip": item["node_ip"]}
            for item in reversed(my_node.finger_table)
            if item.get("node_id") is not None
            and item.get("node_ip") != my_node.ip_address
            and item.get("node_ip") not in visited
            and in_interval(item.get("node_id"), my_node.id, target_id, inclusive_end=False)
        ]
        candidates.extend(finger_candidates)
        candidates.extend(my_node.successor_list)

    deduped = []
    seen = set()
    for candidate in candidates:
        node_ip = candidate.get("node_ip")
        node_id = candidate.get("node_id")
        if not node_ip or node_id is None:
            continue
        if node_ip in seen or node_ip in visited or node_ip == my_node.ip_address:
            continue
        seen.add(node_ip)
        deduped.append({"node_id": node_id, "node_ip": node_ip})
    return deduped


def _lookup_successor(target_id, hop_count=0, path=None, visited=None, max_hops=None):
    max_hops = max_hops or LOOKUP_MAX_HOPS
    path = _append_current(path or [])
    visited = set(visited or set())

    if my_node.ip_address in visited:
        return _successor_result(target_id, hop_count, path, "visited_loop"), 200
    visited.add(my_node.ip_address)

    if hop_count >= max_hops:
        return _successor_result(target_id, hop_count, path, "max_hops_fallback"), 200

    _ensure_live_successor()
    if my_node.check_is_my_successor(target_id):
        return _successor_result(target_id, hop_count, path, "successor_interval"), 200

    for next_node in _candidate_nodes(target_id, visited):
        next_ip = next_node["node_ip"]
        try:
            resp = requests.get(
                _url(next_ip, "/find_successor"),
                params={
                    "id": target_id,
                    "hop_count": hop_count + 1,
                    "path": _encode_path(path),
                    "visited": _encode_visited(visited),
                    "max_hops": max_hops,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json(), 200
        except requests.exceptions.RequestException:
            my_node.remove_known_node(next_ip)
            visited.add(next_ip)

    return _successor_result(target_id, hop_count, path, "local_fallback"), 200


def _replicate_to_successor(record):
    _ensure_live_successor()
    if my_node.successor_ip == my_node.ip_address:
        return None

    replica_payload = {
        "record": record,
        "owner": {"node_id": my_node.id, "node_ip": my_node.ip_address},
    }
    try:
        resp = requests.post(
            _url(my_node.successor_ip, "/internal/resources/replica"),
            json=replica_payload,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return {"node_id": my_node.successor_id, "node_ip": my_node.successor_ip}
    except requests.exceptions.RequestException:
        my_node.remove_known_node(my_node.successor_ip)
    return None


def _store_primary_here(record):
    my_node.store_primary(record)
    return _replicate_to_successor(record)


def _resource_response(resource_key, lookup_result, source, record):
    expected = build_resource_record(resource_key)
    owner = {"node_id": lookup_result["node_id"], "node_ip": lookup_result["node_ip"]}
    return {
        "found": record is not None,
        "resource_id": expected["ring_id"],
        "sha1_hex": expected["sha1_hex"],
        "owner": owner,
        "source": source,
        "hops": lookup_result["hops"],
        "path": lookup_result["path"],
        "value": record.get("value") if record else None,
    }


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "node_id": my_node.id,
            "node_ip": my_node.ip_address,
        }
    )


@app.route("/info", methods=["GET"])
def get_info():
    return jsonify(my_node.info())


@app.route("/find_successor", methods=["GET"])
def api_find_successor():
    target_id = request.args.get("id", type=int)
    if target_id is None:
        return jsonify({"error": "missing id"}), 400
    if target_id < 0 or target_id >= MAX_NODES:
        return jsonify({"error": f"id must be in [0, {MAX_NODES - 1}]"}), 400

    hop_count = request.args.get("hop_count", default=0, type=int)
    max_hops = request.args.get("max_hops", default=LOOKUP_MAX_HOPS, type=int)
    path = _parse_path(request.args.get("path"))
    visited = _parse_visited(request.args.get("visited"))

    result, status = _lookup_successor(
        target_id,
        hop_count=hop_count,
        path=path,
        visited=visited,
        max_hops=max_hops,
    )
    return jsonify(result), status


@app.route("/get_predecessor", methods=["GET"])
def api_get_predecessor():
    return jsonify(
        {
            "predecessor_id": my_node.predecessor_id,
            "predecessor_ip": my_node.predecessor_ip,
        }
    )


@app.route("/notify", methods=["POST"])
def api_notify():
    data = request.get_json(silent=True) or {}
    n_id = data.get("id")
    n_ip = data.get("ip")
    if n_id is None or not n_ip:
        return jsonify({"error": "missing id or ip"}), 400

    with my_node.lock:
        should_update = (
            my_node.predecessor_id is None
            or in_interval(n_id, my_node.predecessor_id, my_node.id, inclusive_end=False)
        )
        if should_update:
            my_node.predecessor_id = int(n_id)
            my_node.predecessor_ip = n_ip

    return jsonify({"status": "ok"})


@app.route("/resources", methods=["POST"])
def api_put_resource():
    data = request.get_json(silent=True) or {}
    resource_key = data.get("resource_key")
    if not resource_key:
        return jsonify({"error": "missing resource_key"}), 400

    record = build_resource_record(resource_key, data.get("value"))
    lookup_result, status = _lookup_successor(record["ring_id"])
    if status != 200:
        return jsonify(lookup_result), status

    owner_ip = lookup_result["node_ip"]
    if owner_ip == my_node.ip_address:
        replicated_to = _store_primary_here(record)
    else:
        try:
            resp = requests.post(
                _url(owner_ip, "/internal/resources/primary"),
                json={"record": record},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return jsonify(resp.json()), resp.status_code
            replicated_to = resp.json().get("replicated_to")
        except requests.exceptions.RequestException:
            my_node.remove_known_node(owner_ip)
            return jsonify({"error": f"owner {owner_ip} is unavailable"}), 503

    return jsonify(
        {
            "stored": True,
            "resource_key": resource_key,
            "resource_id": record["ring_id"],
            "sha1_hex": record["sha1_hex"],
            "owner": {"node_id": lookup_result["node_id"], "node_ip": owner_ip},
            "replicated_to": replicated_to,
            "hops": lookup_result["hops"],
            "path": lookup_result["path"],
        }
    )


@app.route("/resources/<path:resource_key>", methods=["GET"])
def api_get_resource(resource_key):
    record_hint = build_resource_record(resource_key)
    lookup_result, status = _lookup_successor(record_hint["ring_id"])
    if status != 200:
        return jsonify(lookup_result), status

    owner_ip = lookup_result["node_ip"]
    if owner_ip == my_node.ip_address:
        source, record = my_node.get_resource(resource_key)
        return jsonify(_resource_response(resource_key, lookup_result, source, record))

    try:
        resp = requests.get(
            _url(owner_ip, f"/internal/resources/{resource_key}"),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return jsonify(resp.json()), resp.status_code
        data = resp.json()
        return jsonify(
            _resource_response(
                resource_key,
                lookup_result,
                data.get("source", "missing"),
                data.get("record"),
            )
        )
    except requests.exceptions.RequestException:
        my_node.remove_known_node(owner_ip)
        source, record = my_node.get_resource(resource_key)
        return jsonify(_resource_response(resource_key, lookup_result, source, record))


@app.route("/internal/resources/primary", methods=["POST"])
def internal_store_primary():
    data = request.get_json(silent=True) or {}
    record = data.get("record")
    if not record or not record.get("resource_key"):
        return jsonify({"error": "missing record"}), 400

    replicated_to = _store_primary_here(record)
    return jsonify({"stored": True, "replicated_to": replicated_to})


@app.route("/internal/resources/replica", methods=["POST"])
def internal_store_replica():
    data = request.get_json(silent=True) or {}
    record = data.get("record")
    owner = data.get("owner")
    if not record or not owner:
        return jsonify({"error": "missing record or owner"}), 400

    my_node.store_replica(record, owner)
    return jsonify({"stored": True})


@app.route("/internal/resources/<path:resource_key>", methods=["GET"])
def internal_get_resource(resource_key):
    source, record = my_node.get_resource(resource_key)
    return jsonify({"found": record is not None, "source": source, "record": record})


def join_network():
    if IS_SEED or not KNOWN_NODE:
        print(f"[{NODE_NAME}] seed node started with id={my_node.id}")
        return

    print(f"[{NODE_NAME}] joining through {KNOWN_NODE} with id={my_node.id}")
    time.sleep(2)

    try:
        resp = requests.get(
            _url(KNOWN_NODE, "/find_successor"),
            params={"id": my_node.id},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            my_node.set_successor(data["node_id"], data["node_ip"])
            requests.post(
                _url(my_node.successor_ip, "/notify"),
                json={"id": my_node.id, "ip": my_node.ip_address},
                timeout=REQUEST_TIMEOUT,
            )
            print(f"[{NODE_NAME}] joined; successor={my_node.successor_ip}")
        else:
            print(f"[{NODE_NAME}] join failed: {resp.text}")
    except requests.exceptions.RequestException as exc:
        print(f"[{NODE_NAME}] cannot join through {KNOWN_NODE}: {exc}")


if __name__ == "__main__":
    join_network()
    start_background_tasks(my_node)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
