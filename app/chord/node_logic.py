from threading import RLock

from app.utils.hashing import M, MAX_NODES, get_hash

SUCCESSOR_LIST_SIZE = 3


def in_interval(val, start, end, inclusive_end=False):
    """Check whether val is in (start, end) or (start, end] on the ring."""
    if start == end:
        return True

    if start < end:
        return start < val <= end if inclusive_end else start < val < end

    return (start < val or val <= end) if inclusive_end else (start < val or val < end)


def clockwise_distance(start, end):
    return (end - start) % MAX_NODES


def _valid_node(node):
    return (
        isinstance(node, dict)
        and node.get("node_id") is not None
        and bool(node.get("node_ip"))
    )


class ChordNode:
    def __init__(self, node_name, ip_address, port=5000):
        self.node_name = node_name
        self.ip_address = ip_address
        self.port = port
        self.id = get_hash(f"{ip_address}:{port}")
        self.lock = RLock()

        self.successor_id = self.id
        self.successor_ip = self.ip_address
        self.successor_list = [self.descriptor()]

        self.predecessor_id = None
        self.predecessor_ip = None

        self.finger_table = []
        self.resources_primary = {}
        self.resources_replica = {}
        self._init_finger_table()

    def descriptor(self):
        return {"node_id": self.id, "node_ip": self.ip_address}

    def _init_finger_table(self):
        for i in range(M):
            start = (self.id + (2 ** i)) % MAX_NODES
            self.finger_table.append(
                {
                    "start": start,
                    "node_id": self.id,
                    "node_ip": self.ip_address,
                }
            )

    def _dedupe_nodes(self, nodes, include_self_if_empty=True):
        deduped = []
        seen = set()
        for node in nodes:
            if not _valid_node(node):
                continue
            key = node["node_ip"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"node_id": int(node["node_id"]), "node_ip": node["node_ip"]})

        if include_self_if_empty and not deduped:
            deduped.append(self.descriptor())
        return deduped[:SUCCESSOR_LIST_SIZE]

    def set_successor(self, node_id, node_ip):
        with self.lock:
            new_successor = {"node_id": int(node_id), "node_ip": node_ip}
            self.successor_id = new_successor["node_id"]
            self.successor_ip = new_successor["node_ip"]
            self.successor_list = self._dedupe_nodes(
                [new_successor] + self.successor_list
            )

    def set_successor_list(self, nodes):
        with self.lock:
            self.successor_list = self._dedupe_nodes(nodes)
            first = self.successor_list[0]
            self.successor_id = first["node_id"]
            self.successor_ip = first["node_ip"]

    def remove_known_node(self, node_ip):
        with self.lock:
            self.successor_list = [
                node for node in self.successor_list if node["node_ip"] != node_ip
            ]
            if not self.successor_list:
                self.successor_list = [self.descriptor()]

            if self.successor_ip == node_ip:
                first = self.successor_list[0]
                self.successor_id = first["node_id"]
                self.successor_ip = first["node_ip"]

            for entry in self.finger_table:
                if entry.get("node_ip") == node_ip:
                    entry["node_id"] = self.id
                    entry["node_ip"] = self.ip_address

    def known_nodes(self, excluded_ips=None):
        excluded_ips = excluded_ips or set()
        candidates = []
        candidates.extend(reversed(self.finger_table))
        candidates.extend(self.successor_list)
        return [
            node
            for node in self._dedupe_nodes(candidates, include_self_if_empty=False)
            if node["node_ip"] not in excluded_ips and node["node_ip"] != self.ip_address
        ]

    def info(self):
        with self.lock:
            return {
                "node_name": self.node_name,
                "id": self.id,
                "successor_id": self.successor_id,
                "successor_ip": self.successor_ip,
                "successor_list": list(self.successor_list),
                "predecessor_id": self.predecessor_id,
                "predecessor_ip": self.predecessor_ip,
                "finger_table": list(self.finger_table),
                "resources_primary_count": len(self.resources_primary),
                "resources_replica_count": len(self.resources_replica),
            }

    def closest_preceding_node(self, target_id, excluded_ips=None):
        excluded_ips = excluded_ips or set()
        with self.lock:
            for finger in reversed(self.finger_table):
                finger_node_id = finger.get("node_id")
                finger_node_ip = finger.get("node_ip")
                if finger_node_id is None or not finger_node_ip:
                    continue
                if finger_node_ip in excluded_ips or finger_node_id == self.id:
                    continue
                if in_interval(finger_node_id, self.id, target_id, inclusive_end=False):
                    return {"node_id": finger_node_id, "node_ip": finger_node_ip}

        return self.descriptor()

    def check_is_my_successor(self, target_id):
        with self.lock:
            return in_interval(target_id, self.id, self.successor_id, inclusive_end=True)

    def store_primary(self, record):
        with self.lock:
            self.resources_primary[record["resource_key"]] = dict(record)

    def store_replica(self, record, owner):
        replica = dict(record)
        replica["owner"] = owner
        with self.lock:
            self.resources_replica[record["resource_key"]] = replica

    def get_resource(self, resource_key):
        with self.lock:
            if resource_key in self.resources_primary:
                return "primary", dict(self.resources_primary[resource_key])
            if resource_key in self.resources_replica:
                return "replica", dict(self.resources_replica[resource_key])
        return "missing", None
