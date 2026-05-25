import threading
import time

import requests

from app.chord.node_logic import in_interval
from app.utils.hashing import M, MAX_NODES

PORT = 5000
REQUEST_TIMEOUT = 2


def _url(node_ip, path):
    return f"http://{node_ip}:{PORT}{path}"


def _is_alive(node, node_ip):
    if node_ip == node.ip_address:
        return True
    try:
        resp = requests.get(_url(node_ip, "/health"), timeout=REQUEST_TIMEOUT)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _promote_live_successor(node, failed_ip=None):
    if failed_ip:
        node.remove_known_node(failed_ip)

    candidates = node.successor_list + node.known_nodes(excluded_ips={failed_ip} if failed_ip else set())
    for candidate in candidates:
        candidate_ip = candidate["node_ip"]
        if candidate_ip == node.ip_address:
            continue
        if _is_alive(node, candidate_ip):
            node.set_successor(candidate["node_id"], candidate_ip)
            return True

    node.set_successor(node.id, node.ip_address)
    return False


def stabilize(node):
    """Periodically repair successor/predecessor pointers and successor list."""
    while True:
        time.sleep(2)
        successor_ip = node.successor_ip

        if not _is_alive(node, successor_ip):
            print(f"[{node.node_name}] successor {successor_ip} is down; promoting backup")
            _promote_live_successor(node, failed_ip=successor_ip)
            continue

        try:
            pred_resp = requests.get(
                _url(successor_ip, "/get_predecessor"), timeout=REQUEST_TIMEOUT
            )
            if pred_resp.status_code == 200:
                data = pred_resp.json()
                x_id = data.get("predecessor_id")
                x_ip = data.get("predecessor_ip")
                if x_id is not None and x_ip and in_interval(
                    x_id, node.id, node.successor_id, inclusive_end=False
                ):
                    node.set_successor(x_id, x_ip)
                    successor_ip = x_ip

            info_resp = requests.get(_url(successor_ip, "/info"), timeout=REQUEST_TIMEOUT)
            if info_resp.status_code == 200:
                successor_info = info_resp.json()
                merged = [
                    {
                        "node_id": node.successor_id,
                        "node_ip": node.successor_ip,
                    }
                ] + successor_info.get("successor_list", [])
                node.set_successor_list(merged)

            requests.post(
                _url(node.successor_ip, "/notify"),
                json={"id": node.id, "ip": node.ip_address},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException:
            print(f"[{node.node_name}] lost contact with successor {successor_ip}")
            _promote_live_successor(node, failed_ip=successor_ip)


def fix_fingers(node):
    """Refresh one finger-table entry per second using normal Chord lookup."""
    next_finger = 0
    while True:
        time.sleep(1)
        next_finger = (next_finger + 1) % M
        target_id = (node.id + (2 ** next_finger)) % MAX_NODES

        try:
            resp = requests.get(
                _url("localhost", f"/find_successor?id={target_id}"),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                node.finger_table[next_finger]["node_id"] = data["node_id"]
                node.finger_table[next_finger]["node_ip"] = data["node_ip"]
        except requests.exceptions.RequestException:
            pass


def start_background_tasks(node):
    t1 = threading.Thread(target=stabilize, args=(node,), daemon=True)
    t2 = threading.Thread(target=fix_fingers, args=(node,), daemon=True)
    t1.start()
    t2.start()
