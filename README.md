# Remote Hardware Lab

Remote Hardware Lab là nền tảng web giúp người dùng viết mã, biên dịch firmware và nạp firmware vào thiết bị thật từ xa thông qua hàng đợi FIFO. Hệ thống được thiết kế theo hướng nhiều service, cập nhật thời gian thực qua WebSocket và tách rõ luồng người dùng với luồng quản trị thiết bị.

## Điểm nổi bật

- Workspace theo từng người dùng và từng project.
- File manager kiểu IDE: tạo, đổi tên, xóa, kéo thả, copy/cut/paste.
- Monaco Editor nhiều tab, có cảnh báo file chưa lưu và auto-save.
- Compile độc lập với thiết bị qua service Arduino CLI.
- Flash firmware qua hàng đợi FIFO riêng cho từng thiết bị.
- Serial monitor realtime sau khi flash thành công.
- Lịch sử flash có log compile, log flash và serial output.
- Admin quản lý thiết bị theo 3 chế độ: `free`, `share`, `block`.
- Cập nhật realtime trạng thái thiết bị, queue và serial session qua Socket.IO.

## Kiến trúc tổng thể

```text
Browser
  |
  v
Nginx reverse proxy (:80)
  |-- Frontend (React + Vite + Nginx)
  |-- Backend API + Socket.IO (Flask)
          |-- MySQL
          |-- Compiler service (FastAPI + Arduino CLI)
          |-- Broker service (FastAPI + esptool.py / custom protocol)
          |-- Queue worker + serial capture orchestration
  |
  +-- Hardware Manager (USB listener -> backend internal API)
```

## Công nghệ sử dụng

| Thành phần | Stack |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Monaco Editor, Zustand, Socket.IO Client |
| Backend | Flask, Flask-SocketIO, Eventlet, MySQL Connector, JWT |
| Compiler | FastAPI, Arduino CLI |
| Broker | FastAPI, pyserial, esptool.py |
| Hardware detection | Python, `serial.tools.list_ports` |
| Database | MySQL 8 |
| Deployment local | Docker Compose, Nginx |

## Tính năng chính

### Người dùng

- Đăng ký, đăng nhập, xác thực JWT.
- Tạo và quản lý project trong workspace riêng.
- Soạn thảo mã nguồn nhiều file, nhiều tab.
- Biên dịch firmware cho `ESP32`, `ESP8266`, `Arduino Uno`.
- Gửi yêu cầu nạp firmware vào hàng đợi.
- Theo dõi trạng thái `waiting`, `flashing`, `success`, `failed`, `cancelled`.
- Xem serial output realtime và lịch sử nạp.

### Quản trị viên

- Xem toàn bộ thiết bị đang có trong hệ thống.
- Chỉnh tên hiển thị cho thiết bị.
- Chuyển `usage_mode` giữa `free`, `share`, `block`.
- Cấp quyền share thiết bị theo user và thời hạn.
- Thu hồi quyền share và quản lý người dùng.

## Cấu trúc thư mục

```text
remote-hardware-lab/
├── backend/            # Flask API, auth, workspace API, Socket.IO, queue worker
├── broker/             # Flash firmware và serial capture
├── compiler/           # Arduino CLI compile service
├── database/           # init.sql và các migration
├── frontend/           # React + TypeScript + Vite
├── hardware_manager/   # USB listener báo cắm/rút thiết bị
├── nginx/              # Reverse proxy cho frontend/backend/socket.io
├── QUANLYUSER/         # Dữ liệu runtime được mount vào backend
├── docker-compose.yml
└── phase3-master-plan.md
```

## Khởi động nhanh với Docker Compose

### Yêu cầu

- Docker
- Docker Compose
- Máy host có quyền truy cập serial/USB nếu muốn test flash thiết bị thật
- Môi trường Linux hoặc WSL2 phù hợp hơn cho các mount như `/dev`

### 1. Chuẩn bị biến môi trường

Tạo file `.env` ở thư mục gốc:

```env
MYSQL_ROOT_PASSWORD=change-me
MYSQL_DATABASE=remote_lab
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=change-me
DB_HOST=database
DB_USER=root
DB_PASSWORD=change-me
DB_NAME=remote_lab
DB_PORT=3306
INTERNAL_API_KEY=change-me
LISTENER_POLLING_INTERVAL=5
BROKER_URL=http://broker:8000
```

Tạo file `frontend/.env`:

```env
VITE_API_URL=http://localhost:5000
```

Ghi chú:

- Khi truy cập từ máy khác trong cùng mạng LAN, frontend đã có fallback để tránh lỗi hardcode `localhost`.
- Để đầy đủ tính năng realtime, nên truy cập ứng dụng qua reverse proxy `http://localhost` hoặc IP của máy chủ ở cổng `80`.

### 2. Build và chạy hệ thống

```bash
docker compose up --build -d
```

### 3. Truy cập ứng dụng

| URL | Mục đích |
| --- | --- |
| `http://localhost` | Cổng truy cập chính, có đủ API, SSE và WebSocket |
| `http://localhost:5000/api/healthcheck` | Kiểm tra backend |
| `http://localhost:8000/healthcheck` | Kiểm tra broker |
| `http://localhost:9000/healthcheck` | Kiểm tra compiler |

Tài khoản admin mặc định trong môi trường phát triển:

- Username: `admin`
- Password: `admin`

## Luồng sử dụng chính

1. Người dùng đăng nhập và tạo project trong Workspace.
2. Soạn thảo mã nguồn bằng file tree + Monaco Editor.
3. Chọn board rồi bấm Compile để tạo firmware `.bin`.
4. Chọn thiết bị khả dụng và gửi yêu cầu flash vào queue.
5. Backend worker lấy request theo FIFO, khóa thiết bị, gọi broker để flash.
6. Sau khi flash xong, hệ thống stream serial output và lưu log vào lịch sử.

## Các service trong `docker-compose.yml`

| Service | Vai trò | Port public |
| --- | --- | --- |
| `database` | MySQL | `3306` |
| `backend` | REST API, Socket.IO, queue worker | `5000` |
| `frontend` | Static frontend build | `3000 -> 80` |
| `nginx` | Reverse proxy chính | `80` |
| `hardware_manager` | Lắng nghe cắm/rút thiết bị | không public |
| `broker` | Flash firmware, serial capture | `8000` |
| `compiler` | Compile firmware | `9000` |

## Một số lệnh hữu ích

```bash
docker compose up --build -d
docker compose logs -f backend
docker compose logs -f compiler
docker compose logs -f broker
docker compose down
```

## Lưu ý triển khai

- Cổng `:3000` chỉ là frontend container; cổng truy cập khuyến nghị vẫn là `:80` để WebSocket và reverse proxy hoạt động đồng bộ.
- `backend` mount Docker socket và dữ liệu người dùng để quản lý workspace/container theo user.
- `hardware_manager` và `broker` cần quyền truy cập thiết bị serial từ máy host.
- `flash_queue` và `usage_mode` đã được tích hợp theo kế hoạch phase 3 hoàn chỉnh.

## Tài liệu liên quan

- `phase3-master-plan.md`: kế hoạch và checklist hoàn thành phase 3
- `map.md`: bản đồ cấu trúc thư mục
- `database/init.sql`: schema khởi tạo và seed dữ liệu ban đầu

