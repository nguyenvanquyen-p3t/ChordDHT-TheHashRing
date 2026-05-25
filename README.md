# Chord DHT Project

Dự án triển khai DHT Chord đơn giản cho đồ án Cơ sở dữ liệu phân tán.

## Mapping với yêu cầu đề bài

- Hash ring: `app/utils/hashing.py` dùng SHA-1 và ánh xạ vào không gian `2^16`.
- Node_IDs: Docker Compose sinh tới 50 node, mỗi node hash từ `hostname:port`.
- Resource_IDs: `analysis/simulate_queries.py` sinh 1.000 resource keys `resource_0001..resource_1000`, kèm `sha1_hex` và `ring_id`.
- Finger table: mỗi node giữ `M=16` finger entries và refresh bằng `fix_fingers`.
- Lookup: `GET /find_successor?id=<ring_id>` trả về owner, hop count, path và cách resolve.
- Metric: `analysis/run_experiments.py` chạy thực nghiệm cho `N=10,20,30,40,50`, ghi CSV và vẽ chart.
- Failure demo: mỗi node giữ successor list 3 phần tử; khi successor chết, node chọn backup còn sống.

## Chạy 50 node

```powershell
python scripts/generate_compose.py --nodes 50
docker compose up -d --build
```

Chờ 20-30 giây để các node stabilize, sau đó xem node 0:

```powershell
Invoke-RestMethod http://localhost:5000/info
```

## API demo

Lookup một key trên ring:

```powershell
Invoke-RestMethod "http://localhost:5000/find_successor?id=12345"
```

Insert resource:

```powershell
Invoke-RestMethod -Method Post http://localhost:5000/resources `
  -ContentType "application/json" `
  -Body '{"resource_key":"resource_0001","value":"demo value"}'
```

Get resource:

```powershell
Invoke-RestMethod http://localhost:5000/resources/resource_0001
```

## Demo lỗi node (The Proof)

1. Chạy network 50 node và insert resource.
2. Ghi lại owner/path của resource bằng `GET /resources/<resource_key>`.
3. Tắt một node:

```powershell
docker stop chord-node-10
```

4. Chờ 6-10 giây để stabilize.
5. Lookup lại resource hoặc một key khác. Nếu key thuộc node bị tắt, kết quả có thể trả `source=replica` trên successor sống.

## Chạy thực nghiệm hop count

Chạy riêng với network đang bật:

```powershell
python analysis/simulate_queries.py --node-count 50 --queries 1000 --output analysis/results/hop_results.csv
```

Chạy toàn bộ N=10..50, mỗi lần tự tạo compose và restart Docker:

```powershell
python analysis/run_experiments.py --node-counts 10,20,30,40,50 --queries 1000
```

Kết quả:

- CSV: `analysis/results/hop_results.csv`
- Chart: `chord_analysis_chart.png`

## Lý do hop count gần O(log N)

Mỗi finger entry thứ `i` trỏ tới successor của vị trí `node_id + 2^i`. Khi lookup, node chọn finger xa nhất nhưng vẫn đứng trước target. Cách chọn này làm khoảng cách còn lại đến target giảm theo bước lũy thừa, nên số hop kỳ vọng tăng theo `O(log N)`. CSV và chart trong `analysis/results` dùng để đối chiếu số liệu đo được với đường tham chiếu `0.5 * log2(N)`.
