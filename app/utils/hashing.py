import hashlib

# Cấu hình không gian Vòng băm (M-bit)
M = 10
MAX_NODES = 2 ** M  # 1024 vị trí (từ 0 đến 1023)

def get_hash(key_string):
    """
    Băm một chuỗi (ví dụ: '192.168.1.5:5000' hoặc 'resource_1') 
    thành một ID nguyên nằm trong khoảng [0, MAX_NODES - 1].
    """
    # 1. Băm chuỗi bằng SHA-1 (đầu ra là bytes)
    hash_bytes = hashlib.sha1(key_string.encode('utf-8')).digest()
    
    # 2. Chuyển đổi bytes thành số nguyên lớn
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    
    # 3. Ép số nguyên khổng lồ này nằm gọn trong Vòng băm bằng phép chia lấy dư
    return hash_int % MAX_NODES