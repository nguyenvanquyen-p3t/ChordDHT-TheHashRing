import os
import time
import requests
from flask import Flask, request, jsonify
from app.chord.node_logic import ChordNode, in_interval
from app.chord.stabilize import start_background_tasks

app = Flask(__name__)

# 1. Đọc biến môi trường từ docker-compose
NODE_NAME = os.environ.get("HOSTNAME", "node-unknown")
IS_SEED = os.environ.get("IS_SEED", "False") == "True"
KNOWN_NODE = os.environ.get("KNOWN_NODE", None)
PORT = 5000

# 2. Khởi tạo "Bộ não" của Nút
# IP của Nút chính là tên container do Docker tự động phân giải (DNS)
my_node = ChordNode(node_name=NODE_NAME, ip_address=NODE_NAME, port=PORT)


# ==========================================
# CÁC API GIAO TIẾP MẠNG CƠ BẢN
# ==========================================

@app.route('/info', methods=['GET'])
def get_info():
    """Trả về trạng thái hiện tại của Nút (Dùng để bạn debug và quay video đồ án)"""
    return jsonify(my_node.info())

@app.route('/find_successor', methods=['GET'])
def api_find_successor():
    target_id = request.args.get('id', type=int)
    # Lấy giá trị hop_count từ URL, mặc định là 0 nếu truy vấn mới bắt đầu
    hop_count = request.args.get('hop_count', default=0, type=int) 
    
    if target_id is None:
        return jsonify({"error": "Thiếu tham số id"}), 400

    # BƯỚC 1: Nếu thuộc về Successor sát vách -> Trả về kết quả kèm số hops hiện tại
    if my_node.check_is_my_successor(target_id):
        return jsonify({
            "node_id": my_node.successor_id,
            "node_ip": my_node.successor_ip,
            "hops": hop_count
        })

    # BƯỚC 2: Tìm Nút xa nhất trong Finger Table
    next_node = my_node.closest_preceding_node(target_id)
    
    # BƯỚC 3: Nếu quẩn lại chính mình
    if next_node["node_id"] == my_node.id:
        return jsonify({
            "node_id": my_node.successor_id,
            "node_ip": my_node.successor_ip,
            "hops": hop_count
        })

    # BƯỚC 4: Chuyển tiếp truy vấn và CỘNG THÊM 1 VÀO HOP_COUNT
    try:
        url = f"http://{next_node['node_ip']}:{PORT}/find_successor?id={target_id}&hop_count={hop_count + 1}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"error": "Lỗi từ Nút trung gian"}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({
            "node_id": my_node.successor_id,
            "node_ip": my_node.successor_ip,
            "hops": hop_count
        })


# ==========================================
# QUÁ TRÌNH KHỞI ĐỘNG (BOOTSTRAPPING)
# ==========================================

def join_network():
    """Hàm chạy ngầm khi khởi động để xin gia nhập mạng"""
    if IS_SEED or not KNOWN_NODE:
        print(f"[{NODE_NAME}] Tôi là Seed Node. Bắt đầu tạo Vòng băm mới.")
        return

    print(f"[{NODE_NAME}] Đang xin gia nhập mạng thông qua {KNOWN_NODE}...")
    
    # Đợi 2 giây để đảm bảo Seed Node đã khởi động xong API
    time.sleep(2) 
    
    try:
        # Gửi request hỏi Seed Node xem ai là Successor của tôi (my_node.id)
        url = f"http://{KNOWN_NODE}:{PORT}/find_successor?id={my_node.id}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            # Cập nhật Successor của mình bằng kết quả trả về
            my_node.successor_id = data["node_id"]
            my_node.successor_ip = data["node_ip"]
            print(f"[{NODE_NAME}] Đã gia nhập thành công! Successor của tôi là {my_node.successor_ip}")
        else:
            print(f"[{NODE_NAME}] Lỗi khi xin gia nhập: {response.text}")
    except Exception as e:
        print(f"[{NODE_NAME}] Không thể kết nối tới {KNOWN_NODE}: {e}")

@app.route('/get_predecessor', methods=['GET'])
def api_get_predecessor():
    """Trả về thông tin Predecessor hiện tại của Nút"""
    return jsonify({
        "predecessor_id": my_node.predecessor_id,
        "predecessor_ip": my_node.predecessor_ip
    })

@app.route('/notify', methods=['POST'])
def api_notify():
    """
    Nút khác gọi API này để thông báo: "Tôi nghĩ tôi là Predecessor của bạn"
    """
    data = request.json
    n_id = data.get("id")
    n_ip = data.get("ip")
    
    # Nếu tôi chưa có Predecessor, HOẶC Nút mới (n) này nằm giữa Predecessor cũ và tôi
    if my_node.predecessor_id is None or in_interval(n_id, my_node.predecessor_id, my_node.id, inclusive_end=False):
        my_node.predecessor_id = n_id
        my_node.predecessor_ip = n_ip
        print(f"[{NODE_NAME}] Đã cập nhật Predecessor mới là {n_ip}")
        
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    # Xin gia nhập mạng
    join_network()
    
    # BẬT CÁC LUỒNG CHẠY NGẦM ĐỂ TỰ ĐỘNG CẬP NHẬT MẠNG
    start_background_tasks(my_node)
    
    # Khởi động server
    app.run(host='0.0.0.0', port=PORT)