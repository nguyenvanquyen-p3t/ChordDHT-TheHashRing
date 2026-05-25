import hashlib

# Chord identifier space. M=16 gives 65,536 ring positions, enough for
# the required 50 nodes and 1,000 resources while keeping tables readable.
M = 16
MAX_NODES = 2 ** M


def get_sha1_hex(key_string):
    """Return the full SHA-1 digest as a hexadecimal string."""
    return hashlib.sha1(key_string.encode("utf-8")).hexdigest()


def get_hash(key_string):
    """Map a string to an integer position on the Chord ring."""
    return int(get_sha1_hex(key_string), 16) % MAX_NODES


def build_resource_record(resource_key, value=None):
    """Create the stable dataset record used by storage and analysis scripts."""
    sha1_hex = get_sha1_hex(resource_key)
    return {
        "resource_key": resource_key,
        "sha1_hex": sha1_hex,
        "ring_id": int(sha1_hex, 16) % MAX_NODES,
        "value": value if value is not None else f"value_for_{resource_key}",
    }
