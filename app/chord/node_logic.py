from app.utils.hashing import get_hash, MAX_NODES, M

def in_interval(val, start, end, inclusive_end=False):
    """
    Kiểm tra xem 'val' có nằm trong khoảng từ 'start' đến 'end' trên vòng băm không.
    inclusive_end = True tương đương khoảng (start, end]
    inclusive_end = False tương đương khoảng (start, end)
    """
    if start == end:
        return True
    
    if start < end:
        if inclusive_end:
            return start < val <= end
        return start < val < end
    else:
        # Trường hợp vòng qua số 0 (ví dụ: start=1000, end=5)
        if inclusive_end:
            return start < val or val <= end
        return start < val or val < end

class ChordNode:
    def __init__(self, node_name, ip_address, port=5000):
        # Thông tin mạng cơ bản
        self.node_name = node_name
        self.ip_address = ip_address
        self.port = port
        
        # ID của Nút trên Vòng băm (Tọa độ)
        self.id = get_hash(f"{ip_address}:{port}")
        
        # Con trỏ Vòng (Ring Pointers)
        # Khi mới sinh ra và chưa kết nối với ai, Nút sẽ tự trỏ vào chính mình
        self.successor_id = self.id
        self.successor_ip = self.ip_address
        
        self.predecessor_id = None
        self.predecessor_ip = None
        
        # Khởi tạo Bảng định tuyến (Finger Table)
        self.finger_table = []
        self._init_finger_table()

    def _init_finger_table(self):
        """
        Bảng Finger Table gồm M dòng (ví dụ M=10).
        Dòng thứ i sẽ lưu Nút chịu trách nhiệm cho vị trí (node.id + 2^i).
        """
        for i in range(M):
            start = (self.id + (2 ** i)) % MAX_NODES
            self.finger_table.append({
                "start": start,
                "node_id": self.id,      # Ban đầu chưa biết ai, tự gán cho mình
                "node_ip": self.ip_address
            })

    def info(self):
        """Trả về thông tin để hiển thị khi gọi API"""
        return {
            "node_name": self.node_name,
            "id": self.id,
            "successor_id": self.successor_id,
            "predecessor_id": self.predecessor_id,
            "finger_table": self.finger_table
        }
    
    def closest_preceding_node(self, target_id):
        """
        Quét Finger Table từ dưới lên (từ khoảng cách xa nhất về gần nhất).
        Mục tiêu: Tìm Nút xa nhất mà mình biết, NHƯNG không được vượt quá target_id.
        Đây chính là linh hồn của O(log N) - giống tìm kiếm nhị phân.
        """
        # Quét ngược từ dòng M-1 về 0
        for i in range(len(self.finger_table) - 1, -1, -1):
            finger_node_id = self.finger_table[i]["node_id"]
            
            # Nếu Nút trong Finger Table này đã được cập nhật và nằm giữa (self.id, target_id)
            if finger_node_id is not None:
                if in_interval(finger_node_id, self.id, target_id, inclusive_end=False):
                    return self.finger_table[i]
                    
        # Nếu không tìm thấy ai phù hợp hơn, trả về chính mình
        return {"node_id": self.id, "node_ip": self.ip_address}

    def check_is_my_successor(self, target_id):
        """
        Kiểm tra xem target_id có rơi vào vùng quản lý của Successor của mình không.
        Vùng quản lý của Successor là khoảng (self.id, self.successor_id]
        """
        return in_interval(target_id, self.id, self.successor_id, inclusive_end=True)