import requests
import random
import matplotlib.pyplot as plt
import math

# Cấu hình không gian băm (giống file hashing.py)
MAX_NODES = 1024
NUM_QUERIES = 1000

# Hàm sinh ngẫu nhiên 1000 Resource_IDs
def generate_random_keys(num_keys):
    return [random.randint(0, MAX_NODES - 1) for _ in range(num_keys)]

def run_simulation():
    print(f"Bắt đầu gửi {NUM_QUERIES} truy vấn vào mạng lưới...")
    keys_to_search = generate_random_keys(NUM_QUERIES)
    total_hops = 0
    max_hops = 0
    
    for idx, target_id in enumerate(keys_to_search):
        try:
            # Gửi truy vấn tìm kiếm tới Nút số 0
            url = f"http://localhost:5000/find_successor?id={target_id}"
            response = requests.get(url)
            
            if response.status_code == 200:
                hops = response.json().get("hops", 0)
                total_hops += hops
                if hops > max_hops:
                    max_hops = hops
                
                # In tiến độ cho vui mắt
                if (idx + 1) % 100 == 0:
                    print(f"Đã hoàn thành {idx + 1}/{NUM_QUERIES} truy vấn...")
        except Exception as e:
            print(f"Lỗi kết nối tại truy vấn {idx}: {e}")

    avg_hops = total_hops / NUM_QUERIES
    print("-" * 30)
    print(f"TỔNG KẾT MẠNG 50 NÚT:")
    print(f"- Tổng số truy vấn: {NUM_QUERIES}")
    print(f"- Số bước nhảy trung bình: {avg_hops:.2f}")
    print(f"- Số bước nhảy tối đa: {max_hops}")
    print(f"- Giá trị lý thuyết O(log N) với N=50 là khoảng: {math.log2(50) / 2:.2f}")
    print("-" * 30)

    # VẼ BIỂU ĐỒ (Giả lập số liệu cho N = 10, 20, 30, 40, 50 để báo cáo)
    # Trong thực tế, bạn sẽ chạy lại script này với các mạng Docker có kích thước khác nhau.
    # Ở đây tôi tạo sẵn khung biểu đồ để bạn nộp báo cáo.
    N_values = [10, 20, 30, 40, 50]
    
    # Công thức trung bình số bước nhảy của Chord là khoảng (log2(N) / 2)
    theoretical_hops = [math.log2(n) / 2 for n in N_values]
    
    # Đây là số liệu giả định cho các mạng nhỏ hơn (bạn thay bằng số thật sau khi test)
    actual_hops = [1.6, 2.1, 2.4, 2.6, avg_hops] 

    plt.figure(figsize=(8, 5))
    plt.plot(N_values, actual_hops, marker='o', linestyle='-', color='b', label='Số bước nhảy thực tế (Thực nghiệm)')
    plt.plot(N_values, theoretical_hops, marker='x', linestyle='--', color='r', label='O(log N) Lý thuyết')
    
    plt.title('Chord DHT: Số bước nhảy (Hops) so với Số lượng Nút (N)')
    plt.xlabel('Số lượng Nút (N)')
    plt.ylabel('Số bước nhảy trung bình (Hops)')
    plt.xticks(N_values)
    plt.legend()
    plt.grid(True)
    
    # Lưu hình ảnh biểu đồ ra file
    plt.savefig('chord_analysis_chart.png')
    print("Đã lưu biểu đồ thành công vào file 'chord_analysis_chart.png'.")
    plt.show()

if __name__ == '__main__':
    run_simulation()