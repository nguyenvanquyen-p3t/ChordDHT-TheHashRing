import yaml
import os

NUM_NODES = 50
OUTPUT_FILE = "../docker-compose.yml" # Xuất file ra thư mục gốc

compose_dict = {
    "version": "3.8",
    "services": {},
    "networks": {
        "chord_net": {
            "driver": "bridge"
        }
    }
}

# Tạo Seed Node (Nút số 0)
compose_dict["services"]["node-0"] = {
    "build": ".",
    "container_name": "chord-node-0",
    "hostname": "node-0",
    "networks": ["chord_net"],
    "environment": [
        "IS_SEED=True",
        "PYTHONUNBUFFERED=1" # Để log hiện ra terminal ngay lập tức
    ],
    "ports": ["5000:5000"] # Expose port để bạn dễ test Node 0 trên máy thật
}

# Tạo 49 Nút còn lại
for i in range(1, NUM_NODES):
    node_name = f"node-{i}"
    compose_dict["services"][node_name] = {
        "build": ".",
        "container_name": f"chord-node-{i}",
        "hostname": node_name,
        "networks": ["chord_net"],
        "depends_on": ["node-0"],
        "environment": [
            "IS_SEED=False",
            "KNOWN_NODE=node-0",
            "PYTHONUNBUFFERED=1"
        ],
        # Mở thêm một vài port để dễ truy cập từ ngoài (ví dụ Nút 1-5)
        **({"ports": [f"{5000+i}:5000"]} if i <= 5 else {})
    }

# Lấy đường dẫn tuyệt đối để lưu file
script_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(script_dir, OUTPUT_FILE)

with open(output_path, "w") as f:
    yaml.dump(compose_dict, f, default_flow_style=False, sort_keys=False)

print(f"Đã tạo xong file docker-compose.yml cho {NUM_NODES} nodes!")