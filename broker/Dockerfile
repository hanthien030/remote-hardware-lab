# file: broker/Dockerfile

FROM python:3.9-slim

# Thay đổi WORKDIR ra ngoài thư mục code, ví dụ /code
# WORKDIR sẽ là nơi chúng ta thực thi lệnh
WORKDIR /code

# Copy file requirements trước để tận dụng Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ thư mục app vào WORKDIR
# Cấu trúc trong container sẽ là /code/app/main.py
COPY ./app ./app

EXPOSE 8000

# Chạy uvicorn từ /code và chỉ đường dẫn module đầy đủ là "app.main:app"
# Python sẽ hiểu "app" là một package và giải quyết được import tương đối
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]