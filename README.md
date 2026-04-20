# Remote Hardware Lab

Remote Hardware Lab là nền tảng web giúp người dùng viết mã, biên dịch firmware, nạp firmware lên thiết bị thật từ xa và theo dõi trạng thái phần cứng theo thời gian thực. Hệ thống được tách thành nhiều service, có hàng đợi nạp firmware, quản trị thiết bị, và luồng duyệt thiết bị mới trước khi đưa vào sử dụng.

## Trạng thái hiện tại

Hệ thống hiện đã hỗ trợ đầy đủ các luồng chính sau:

- Quản lý workspace theo người dùng và project.
- Soạn thảo mã với Monaco Editor, nhiều tab, lưu file và quản lý cây thư mục.
- Biên dịch project qua compiler service và stream log về giao diện.
- Lưu artifact biên dịch vào thư mục `build/` trong workspace.
- Nạp firmware qua hàng đợi FIFO theo từng thiết bị.
- Theo dõi lịch sử flash, log nạp và serial output sau khi nạp.
- Quản trị thiết bị với cơ chế `pending_review` trước khi cho phép sử dụng.
- Tự động enrich metadata phần cứng cho ESP-class device khi phát hiện thiết bị mới.
- Admin có nút `Check` để đọc thêm metadata cho thiết bị đang chờ duyệt.
- Lọc thông tin phần cứng theo vai trò: admin thấy sâu hơn, user chỉ thấy thông tin cần thiết.
- Hỗ trợ Arduino Uno trong luồng compile, queue flash, broker flash và serial capture.
- Có reconcile khi khởi động để dọn trạng thái `connected` bị stale sau crash/restart.

## Tính năng chính

### Người dùng

- Đăng ký, đăng nhập và xác thực bằng JWT.
- Tạo, xóa project trong workspace cá nhân.
- Quản lý file/thư mục trong project.
- Biên dịch firmware cho board đã chọn và xem log realtime.
- Gửi yêu cầu flash vào hàng đợi với board và baud rate phù hợp.
- Theo dõi request đang chạy, vị trí trong hàng đợi, lịch sử flash và serial output.
- Hủy request khi còn ở trạng thái chờ.

### Quản trị viên

- Xem danh sách thiết bị đã duyệt và thiết bị đang chờ duyệt.
- Duyệt thiết bị mới bằng cách đặt tên và xác nhận `board_class`.
- Xem metadata phần cứng mở rộng như USB serial, MAC, chip family/type, flash size, crystal frequency.
- Dùng nút `Check` để bổ sung metadata cho thiết bị pending còn thiếu thông tin.
- Chuyển `usage_mode` giữa `free`, `share`, `block`.
- Gán thiết bị cho user theo thời hạn, thu hồi quyền chia sẻ và reset thiết bị về `pending_review`.
- Quản lý danh sách người dùng.

### Hệ thống

- Tự phát hiện thiết bị cắm/rút từ host qua `hardware_manager`.
- Gọi broker để probe ESP device và lấy metadata phần cứng.
- Giữ thiết bị ở `block + pending_review` cho đến khi admin xác nhận.
- Khóa thiết bị trong lúc queue worker xử lý flash.
- Phát event realtime cho dashboard, flash queue, lịch sử và serial session.

## Hỗ trợ board

| Board | Compile | Flash từ UI | Artifact | Flash backend |
| --- | --- | --- | --- | --- |
| `esp32` | Có | Có | `.bin` | `esptool` |
| `esp8266` | Có | Có | `.bin` | `esptool` |
| `arduino_uno` | Có | Có | `.hex` | `avrdude` |

Ghi chú:

- ESP32 và ESP8266 có thể được probe để lấy thêm metadata phần cứng.
- Arduino Uno được hỗ trợ theo hướng thay đổi tối thiểu: compile ra `.hex`, enqueue đúng loại artifact, flash bằng `avrdude`, rồi tiếp tục serial capture như các board khác.

## Kiến trúc tổng thể

```text
Browser
  |
  v
Nginx reverse proxy (:80)
  |-- Frontend (React + Vite + Nginx)
  |-- Backend API + Socket.IO (Flask)
          |-- MySQL
          |-- Queue worker (chạy trong backend process)
          |-- Compiler service (FastAPI + Arduino CLI)
          |-- Broker service (FastAPI + esptool / avrdude / pyserial)
  |
  +-- Hardware Manager (USB listener -> backend internal API)
```

## Công nghệ sử dụng

| Thành phần | Stack |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Monaco Editor, Zustand, Socket.IO Client |
| Backend | Flask, Flask-SocketIO, Eventlet, MySQL Connector, JWT |
| Compiler | FastAPI, Arduino CLI |
| Broker | FastAPI, pyserial, esptool, avrdude |
| Hardware detection | Python, `serial.tools.list_ports` |
| Database | MySQL 8 |
| Reverse proxy | Nginx |
| Local deployment | Docker Compose |

## Cấu trúc thư mục

```text
Phase5/
|-- backend/            # Flask API, auth, workspace API, Socket.IO, queue worker
|-- broker/             # Probe thiết bị, flash firmware, serial capture
|-- compiler/           # Arduino CLI compile service
|-- database/           # init.sql và các migration
|-- frontend/           # React + TypeScript + Vite
|-- hardware_manager/   # Listener phát hiện thiết bị cắm/rút
|-- nginx/              # Reverse proxy
|-- docker-compose.yml
`-- README.md
```

## Khởi động nhanh với Docker Compose

### Yêu cầu

- Docker
- Docker Compose
- Máy host có quyền truy cập USB/serial nếu muốn làm việc với thiết bị thật
- Linux hoặc WSL2 phù hợp hơn vì `broker` và `hardware_manager` cần mount `/dev`

### 1. Chuẩn bị biến môi trường

Tạo file `.env` ở thư mục gốc từ `.env.example`:

```env
MYSQL_ROOT_PASSWORD=your_mysql_root_password
MYSQL_DATABASE=remote_lab
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=replace_with_a_strong_random_secret
DB_HOST=database
DB_USER=root
DB_PASSWORD=your_mysql_root_password
DB_NAME=remote_lab
DB_PORT=3306
INTERNAL_API_KEY=replace_with_a_long_random_internal_api_key
LISTENER_POLLING_INTERVAL=5
BROKER_URL=http://broker:8000
```

Tạo file `frontend/.env` từ `frontend/.env.example`:

```env
VITE_API_URL=http://localhost:5000
```

Ghi chú:

- Khi truy cập qua `http://localhost`, frontend hoạt động qua Nginx reverse proxy.
- Frontend đã có fallback same-origin nên truy cập từ máy khác trong cùng LAN vẫn an toàn hơn so với hardcode `localhost`.

### 2. Build và chạy hệ thống

```bash
docker compose up --build -d
```

### 3. Nếu đang nâng cấp một database cũ

Với database mới, schema sẽ được khởi tạo từ `database/init.sql`.

Nếu đang nâng cấp một database đã tồn tại, chạy các migration trong `database/migrations/` theo đúng thứ tự tên file:

- `database/migrations/2026-04-02_phase3c_a_flash_queue_indexes.sql`
- `database/migrations/2026-04-08_phase3d_a_usage_mode.sql`
- `database/migrations/2026-04-13_phase4_batch1_feature_c_baud_rate.sql`
- `database/migrations/2026-04-13_phase4_batch2a_device_review_state.sql`
- `database/migrations/2026-04-13_phase5_batch5a_probe_metadata.sql`

### 4. Truy cập ứng dụng

| URL | Mục đích |
| --- | --- |
| `http://localhost` | Cổng truy cập chính qua Nginx |
| `http://localhost:5000/api/healthcheck` | Backend healthcheck |
| `http://localhost:8000/healthcheck` | Broker healthcheck |
| `http://localhost:9000/healthcheck` | Compiler healthcheck |

Tài khoản admin mặc định trên database mới:

- Username: `admin`
- Password: `admin`

## Các service trong `docker-compose.yml`

| Service | Vai trò | Port public |
| --- | --- | --- |
| `database` | MySQL | `3306` |
| `backend` | REST API, Socket.IO, queue worker | `5000` |
| `frontend` | Static frontend build | `3000 -> 80` |
| `nginx` | Reverse proxy chính | `80` |
| `hardware_manager` | Lắng nghe cắm/rút thiết bị | không public |
| `broker` | Probe, flash firmware, serial capture | `8000` |
| `compiler` | Compile firmware | `9000` |

## Một số endpoint quan trọng

| Endpoint | Mô tả |
| --- | --- |
| `POST /api/auth/login` | Đăng nhập |
| `GET /api/workspace/projects` | Danh sách project |
| `POST /api/workspace/<project>/compile` | Biên dịch project |
| `GET /api/flash/devices?board_type=...` | Lấy danh sách thiết bị hợp lệ để flash |
| `POST /api/flash/requests` | Tạo flash request |
| `GET /api/flash/requests` | Lịch sử flash |
| `POST /api/admin/devices/<tag_name>/approve` | Duyệt thiết bị pending |
| `POST /api/admin/devices/<tag_name>/check` | Admin kiểm tra và enrich metadata pending device |

## Một số lệnh hữu ích

```bash
docker compose up --build -d
docker compose logs -f backend
docker compose logs -f broker
docker compose logs -f compiler
docker compose logs -f hardware_manager
docker compose down
```

## Lưu ý vận hành

- Nên truy cập qua `http://localhost` để frontend, API và WebSocket đi qua cùng reverse proxy.
- `backend` mount Docker socket, `QUANLYUSER/` và volume `workspaces_data` để quản lý runtime data và workspace.
- `broker` và `hardware_manager` cần quyền truy cập thiết bị serial từ host.
- Queue worker chạy bên trong backend process, không có container riêng.
- Thiết bị mới không dùng được ngay: luôn cần admin duyệt trước.
- Dữ liệu phần cứng hiển thị cho user đã được rút gọn; thông tin nhạy hơn chỉ dành cho admin.
- Sau khi host hoặc container restart đột ngột, `hardware_manager` sẽ chạy reconcile một lần để dọn trạng thái kết nối cũ.

## Tài liệu liên quan

- `database/init.sql`: schema khởi tạo và seed dữ liệu mặc định
- `database/migrations/`: các thay đổi schema cho instance đang chạy
- `map.md`: ghi chú cấu trúc repo
- `patterns.md`: một số pattern đang dùng trong dự án
