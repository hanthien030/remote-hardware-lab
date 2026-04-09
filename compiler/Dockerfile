# 1. Kế thừa ngay Base Image mà bạn vừa đẩy lên Hub
FROM hanthien030/remote-lab-compiler-base:latest

WORKDIR /code

# 2. Cài đặt các thư viện Python nhanh chóng
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# 3. Cài các thư viện Arduino (phần này nhẹ, cài rất nhanh)
RUN arduino-cli lib install "ArduinoJson" \
    && arduino-cli lib install "PubSubClient"

# 4. Copy mã nguồn của bạn vào
COPY ./app ./app

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]