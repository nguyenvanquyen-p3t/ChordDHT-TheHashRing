FROM python:3.10-slim

WORKDIR /app

# Copy và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ thư mục app vào trong container
COPY ./app ./app

# Thiết lập biến môi trường để Python nhận diện thư mục app
ENV PYTHONPATH=/app

EXPOSE 5000

# Lệnh khởi chạy
CMD ["python", "app/main.py"]