# Sử dụng image Python 3.9 chính thức
FROM python:3.9-slim

# Thiết lập thư mục làm việc bên trong container
WORKDIR /app

# Sao chép file requirements và cài đặt các thư viện
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn của backend vào container
COPY . .

# Chạy với socketio.run() (eventlet) để hỗ trợ WebSocket
CMD ["python", "run.py"]