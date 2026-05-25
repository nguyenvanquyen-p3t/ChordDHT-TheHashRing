import time
import requests
import threading
from app.utils.hashing import MAX_NODES, M
from app.chord.node_logic import in_interval

PORT = 5000

def stabilize(node):
    """
    Chu kỳ 1: Kiểm tra Nút kế nhiệm (Successor)
    Hỏi Successor xem Predecessor của nó là ai. 
    Nếu có một Nút mới chèn vào giữa, tự động cập nhật lại Successor.
    """
    while True:
        time.sleep(2)  # Chạy mỗi 2 giây
        try:
            # 1. Hỏi Successor xem Predecessor của nó là ai
            url = f"http://{node.successor_ip}:{PORT}/get_predecessor"
            resp = requests.get(url, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                x_id = data.get("predecessor_id")
                x_ip = data.get("predecessor_ip")
                
                # 2. Nếu x nằm giữa tôi và Successor hiện tại -> Cập nhật Successor
                if x_id is not None and in_interval(x_id, node.id, node.successor_id, inclusive_end=False):
                    print(f"[{node.node_name}] Phát hiện Nút mới {x_ip} chen vào giữa. Cập nhật Successor!")
                    node.successor_id = x_id
                    node.successor_ip = x_ip
            
            # 3. Thông báo cho Successor biết: "Tôi đang là Predecessor của bạn đây"
            notify_url = f"http://{node.successor_ip}:{PORT}/notify"
            requests.post(notify_url, json={"id": node.id, "ip": node.ip_address}, timeout=3)
            
        except requests.exceptions.RequestException:
            print(f"[{node.node_name}] CẢNH BÁO: Mất kết nối với Successor ({node.successor_ip})!")
            # Cơ chế chịu lỗi cơ bản: Nếu Successor chết, tạm thời trỏ về chính mình để chờ vòng băm phục hồi
            if node.successor_id != node.id:
                node.successor_id = node.id
                node.successor_ip = node.ip_address


def fix_fingers(node):
    """
    Chu kỳ 2: Làm mới Finger Table liên tục.
    Giúp mạng lưới luôn cập nhật đường đi ngắn nhất (O(log N)) khi có Nút ra/vào.
    """
    next_finger = 0
    while True:
        time.sleep(1) # Chạy mỗi 1 giây
        next_finger = (next_finger + 1) % M
        
        # Vị trí cần tìm trên vòng băm: (node.id + 2^i)
        target_id = (node.id + (2 ** next_finger)) % MAX_NODES
        
        try:
            # Tìm Successor cho vị trí đó bằng API của chính mình
            url = f"http://localhost:{PORT}/find_successor?id={target_id}"
            resp = requests.get(url, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                # Cập nhật vào Finger Table
                node.finger_table[next_finger]["node_id"] = data["node_id"]
                node.finger_table[next_finger]["node_ip"] = data["node_ip"]
        except requests.exceptions.RequestException:
            pass


def start_background_tasks(node):
    """Khởi động các luồng ngầm"""
    t1 = threading.Thread(target=stabilize, args=(node,), daemon=True)
    t2 = threading.Thread(target=fix_fingers, args=(node,), daemon=True)
    t1.start()
    t2.start()