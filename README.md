# Remote Hardware Lab

Remote Hardware Lab là nền tảng web giúp người dùng viết mã, biên dịch firmware và nạp firmware vào thiết bị thật từ xa. Hệ thống được tách thành nhiều service, có cập nhật thời gian thực qua Socket.IO, có hàng đợi nạp firmware, lưu lịch sử flash, và có quy trình duyệt thiết bị trước khi đưa vào sử dụng.

## Điểm nổi bật

- Workspace theo từng người dùng và từng project.
- File manager kiểu IDE: tạo, đổi tên, xóa, kéo thả, copy/cut/paste thư mục và file.
- Monaco Editor nhiều tab, có cảnh báo file chưa lưu và hỗ trợ auto-save.
- Compile toàn bộ project qua SSE, hỗ trợ `.ino`, `.cpp`, `.c`, `.h`, `.hpp`.
- Lưu artifact vào thư mục `build/` trong workspace sau khi compile thành công.
- Queue flash theo thiết bị, có trạng thái `waiting`, `flashing`, `success`, `failed`, `cancelled`.
- Theo dõi queue position, flash log và serial output từ trang lịch sử.
- Live serial session sau flash, có thể dừng chủ động từ giao diện.
- Admin duyệt thiết bị mới trước khi cho phép flash.
- Probe metadata từ broker khi cắm thiết bị: chip type, chip family, MAC, flash size, crystal frequency.
- Quản lý thiết bị theo 3 chế độ `free`, `share`, `block`.
- Cập nhật realtime trạng thái thiết bị, queue flash và serial session qua Socket.IO.

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
          |-- Broker service (FastAPI + esptool/pyserial/custom protocol)
  |
  +-- Hardware Manager (USB listener -> backend internal API)
```

## Công nghệ sử dụng

| Thành phần | Stack |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Monaco Editor, Zustand, Socket.IO Client |
| Backend | Flask, Flask-SocketIO, Eventlet, MySQL Connector, JWT |
| Compiler | FastAPI, Arduino CLI |
| Broker | FastAPI, pyserial, esptool |
| Hardware detection | Python, `serial.tools.list_ports` |
| Database | MySQL 8 |
| Local deployment | Docker Compose, Nginx |

## Tính năng chính

### Người dùng

- Đăng ký, đăng nhập, xác thực bằng JWT.
- Tạo và xóa project trong workspace cá nhân.
- Soạn thảo nhiều file trong cùng project.
- Compile project theo board đã chọn và xem log realtime.
- Lưu firmware artifact vào `build/` để dùng lại cho bước flash.
- Gửi yêu cầu flash vào hàng đợi với lựa chọn thiết bị và baud rate serial.
- Theo dõi active request, queue position, lịch sử flash và serial output.
- Hủy request khi còn ở trạng thái `waiting`.

### Quản trị viên

- Xem danh sách thiết bị đã duyệt và thiết bị đang chờ duyệt.
- Duyệt thiết bị mới bằng cách đặt tên và gán `board_class`.
- Xem metadata probe của thiết bị mới trước khi duyệt.
- Chuyển `usage_mode` giữa `free`, `share`, `block`.
- Chia sẻ thiết bị cho user theo thời hạn.
- Thu hồi quyền share, reset thiết bị về `pending_review`, hoặc xóa record khi an toàn.
- Quản lý danh sách user.

### Hệ thống

- Tự phát hiện thiết bị cắm/rút từ host.
- Probe thiết bị qua broker để lấy metadata phần cứng.
- Khóa thiết bị trong lúc worker xử lý flash.
- Lưu flash log và serial log vào database để khôi phục lại trang lịch sử.
- Phát event realtime cho dashboard, workspace và history.

## Hỗ trợ board

| Board | Compile | Queue flash từ UI | Artifact chính |
| --- | --- | --- | --- |
| `esp32` | Có | Có | `.bin` + có thể kèm manifest flash layout |
| `esp8266` | Có | Có | `.bin` |
| `arduino_uno` | Có | Chưa mở trong UI hiện tại | `.hex` |

Ghi chú:

- Với ESP32, compiler có thể xuất thêm flash layout để broker flash đủ các segment cần thiết, không chỉ mỗi app binary.
- Trong giao diện hiện tại, luồng queue flash đang phục vụ thực tế cho ESP32 và ESP8266.

## Luồng hoạt động chính

### 1. Onboard thiết bị mới

1. `hardware_manager` phát hiện thiết bị cắm vào host.
2. Backend gọi broker để interrogate thiết bị và lấy metadata.
3. Thiết bị mới được tạo ở trạng thái `pending_review` và `block`.
4. Admin vào trang quản trị để đặt tên, chọn `board_class` và approve.
5. Sau khi được duyệt, thiết bị mới xuất hiện trong danh sách có thể dùng.

### 2. Compile và flash qua queue

1. User mở project trong workspace và chỉnh sửa mã nguồn.
2. Frontend gọi backend compile SSE cho toàn bộ project.
3. Backend chuyển tiếp sang compiler service và stream log ngược về UI.
4. Artifact biên dịch được lưu vào `build/` trong workspace người dùng.
5. User mở hộp thoại flash, chọn board, baud rate và thiết bị hợp lệ.
6. Backend tạo flash request trong bảng `flash_queue`.
7. Queue worker claim request, khóa thiết bị, gọi broker để flash và bắt serial.
8. Trạng thái, log flash và serial output được cập nhật realtime và lưu lại.

## Cấu trúc thư mục

```text
remote-hardware-lab/
├── backend/              # Flask API, auth, workspace API, Socket.IO, queue worker
├── broker/               # Flash firmware, interrogate device, serial capture
├── compiler/             # Arduino CLI compile service
├── database/             # init.sql và các migration SQL
├── frontend/             # React + TypeScript + Vite
├── hardware_manager/     # USB listener báo cắm/rút thiết bị
├── nginx/                # Reverse proxy cho frontend/backend/socket.io
├── QUANLYUSER/           # Runtime data mount vào backend
├── docker-compose.yml
└── README.md
```

## Khởi động nhanh với Docker Compose

### Yêu cầu

- Docker
- Docker Compose
- Máy host có quyền truy cập USB/serial nếu muốn flash thiết bị thật
- Linux hoặc WSL2 phù hợp hơn vì `broker` và `hardware_manager` cần mount `/dev`

### 1. Chuẩn bị biến môi trường

Tạo file `.env` ở thư mục gốc từ `.env.example`:

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

Tạo file `frontend/.env` từ `frontend/.env.example`:

```env
VITE_API_URL=http://localhost:5000
```

Ghi chú:

- Khi truy cập qua reverse proxy `http://localhost`, frontend vẫn hoạt động tốt với API cùng origin.
- Khi truy cập từ máy khác trong cùng LAN, frontend đã có fallback để tránh phụ thuộc cứng vào `localhost`.

### 2. Build và chạy hệ thống

```bash
docker compose up --build -d
```

### 3. Nếu bạn đã có database cũ

Bản cài mới sẽ được khởi tạo từ `database/init.sql`. Nếu bạn đang nâng cấp một database đã tồn tại, hãy chạy các file trong `database/migrations/` theo đúng thứ tự tên file.

Các migration hiện có:

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

Tài khoản admin mặc định trong môi trường phát triển:

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
| `broker` | Interrogate, flash firmware, serial capture | `8000` |
| `compiler` | Compile firmware | `9000` |

## Một số lệnh hữu ích

```bash
docker compose up --build -d
docker compose logs -f backend
docker compose logs -f broker
docker compose logs -f compiler
docker compose down
```

## Lưu ý vận hành

- Nên truy cập qua `http://localhost` thay vì `:3000` hoặc `:5000` để WebSocket, API và frontend đi qua cùng reverse proxy.
- `backend` mount Docker socket, `QUANLYUSER/` và volume `workspaces_data` để quản lý workspace và runtime data.
- `broker` và `hardware_manager` cần quyền truy cập thiết bị serial từ host.
- Queue worker được khởi động trong backend process, không có container riêng.
- Thiết bị mới sẽ không dùng được ngay; cần admin approve trước.
- `flash_queue` lưu cả `log_output` và `serial_log`, nên trang history có thể khôi phục lại state sau khi reload.
- Với ESP32, thư mục `build/` có thể chứa thêm file manifest `.flash.json` để mô tả flash layout.

## Tài liệu liên quan

- `database/init.sql`: schema khởi tạo và seed dữ liệu ban đầu
- `database/migrations/`: các migration cho database đang chạy
- `map.md`: ghi chú cấu trúc repo
- `patterns.md`: một số pattern đang dùng trong dự án
