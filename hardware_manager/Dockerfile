# file: hardware_manager/Dockerfile

# Sử dụng image Python 3.9-slim làm base
FROM python:3.9-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Sao chép và cài đặt các thư viện
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép mã nguồn của listener vào container
COPY listener.py .

# Chạy script listener khi container khởi động
CMD ["python", "listener.py"]