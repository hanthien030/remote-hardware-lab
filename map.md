# Project Folder Map

File này là bản đồ cấu trúc thư mục của project `remote-hardware-lab`, tập trung vào phần source code và tài liệu quan trọng.

## Quy ước đọc map

- Chỉ liệt kê các thư mục và file quan trọng
- Bỏ qua bớt thư mục sinh ra tự động như `node_modules`, `dist`, `build`, `__pycache__`
- Mỗi khu vực có mô tả ngắn để dễ định vị khi bảo trì

## Cấu trúc tổng quan

```text
afterPhase2/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── hardware.py
│   │   │   ├── admin_hardware.py
│   │   │   ├── internal.py
│   │   │   └── main.py
│   │   ├── services/
│   │   │   ├── user_service.py
│   │   │   ├── hardware_service.py
│   │   │   └── docker_manager.py
│   │   ├── __init__.py
│   │   ├── auth_decorator.py
│   │   ├── db.py
│   │   └── logger.py
│   ├── tests/
│   ├── config.py
│   ├── run.py
│   ├── requirements.txt
│   └── Dockerfile
├── broker/
│   ├── app/
│   │   ├── handlers/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── protocol.py
│   ├── requirements.txt
│   └── Dockerfile
├── database/
│   └── init.sql
├── firmware/
│   ├── esp32_poc/
│   │   ├── core_kernel/
│   │   │   ├── main/
│   │   │   ├── CMakeLists.txt
│   │   │   └── sdkconfig.defaults
│   │   ├── hello_world/
│   │   │   ├── main/
│   │   │   ├── CMakeLists.txt
│   │   │   ├── README.md
│   │   │   └── pytest_hello_world.py
│   │   ├── secure_bootloader/
│   │   │   ├── main/
│   │   │   ├── CMakeLists.txt
│   │   │   └── partitions.csv
│   │   └── test.txt
│   └── stm32_poc/
├── frontend/
│   ├── public/
│   │   ├── favicon.svg
│   │   └── icons.svg
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   └── index.ts
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── CodeEditor.tsx
│   │   │   ├── FlashFirmwareModal.tsx
│   │   │   ├── LockUnlockModal.tsx
│   │   │   ├── ProtectedRoute.tsx
│   │   │   └── ToastContainer.tsx
│   │   ├── hooks/
│   │   │   └── useToast.ts
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Register.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── DeviceDetail.tsx
│   │   │   └── AdminPanel.tsx
│   │   ├── store/
│   │   │   └── authStore.ts
│   │   ├── styles/
│   │   │   ├── Auth.css
│   │   │   ├── Dashboard.css
│   │   │   ├── DeviceDetail.css
│   │   │   ├── CodeEditor.css
│   │   │   ├── FlashFirmwareModal.css
│   │   │   ├── LockUnlockModal.css
│   │   │   └── Admin.css
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── index.css
│   │   └── constants.ts
│   ├── .env
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── nginx.conf
│   └── Dockerfile
├── hardware_manager/
│   ├── listener.py
│   ├── requirements.txt
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── QUANLYUSER/
├── scripts/
│   └── Bảng Kỹ Thuật API.xlsx
├── .env
├── docker-compose.yml
├── README.md
├── map.md
├── API_DOCUMENTATION.md
├── PROJECT_OVERVIEW_VN.md
├── PHASE2_SUMMARY.md
├── TESTING_GUIDE.md
└── UI_ARCHITECTURE.md
```

## Giải thích theo khu vực

### 1. `backend/`

Đây là trung tâm nghiệp vụ của hệ thống.

- `app/routes/`: định nghĩa các API endpoint
- `app/services/`: chứa logic thao tác user, thiết bị, assignment, Docker
- `auth_decorator.py`: xác thực JWT/session và phân quyền
- `db.py`: kết nối database
- `logger.py`: ghi log hành động
- `config.py`: cấu hình Flask
- `run.py`: entry point chạy app

### 2. `broker/`

Service trung gian nói chuyện trực tiếp với phần cứng.

- `app/main.py`: API FastAPI chính cho flash firmware, ping, interrogate
- `app/protocol.py`: protocol custom cho thiết bị ảo hóa
- `app/handlers/`: khu vực để tách logic xử lý nếu mở rộng thêm

### 3. `database/`

Chứa script khởi tạo database.

- `init.sql`: tạo schema, bảng, dữ liệu mẫu và tài khoản admin mặc định

### 4. `firmware/`

Khu vực proof-of-concept cho firmware và bootloader.

- `esp32_poc/core_kernel/`: firmware lõi cho ESP32
- `esp32_poc/hello_world/`: ví dụ firmware đơn giản
- `esp32_poc/secure_bootloader/`: thử nghiệm bootloader bảo mật
- `stm32_poc/`: chỗ dành cho firmware STM32

Ghi chú:

- Các thư mục `build/` trong khu vực firmware là output sinh tự động, không phải source chính

### 5. `frontend/`

Ứng dụng web React + TypeScript.

- `src/api/`: client Axios và hàm gọi API
- `src/components/`: component dùng lại
- `src/pages/`: các màn hình chính
- `src/store/`: state toàn cục, hiện tại chủ yếu là auth
- `src/styles/`: CSS tách theo page/component
- `public/`: asset public tĩnh

### 6. `hardware_manager/`

Service listener theo dõi thiết bị serial.

- `listener.py`: quét cổng serial, phát hiện cắm/rút, báo về backend

### 7. `nginx/`

Reverse proxy ở mức hệ thống.

- `nginx.conf`: route frontend ở `/` và backend ở `/api/`

### 8. `QUANLYUSER/`

Thư mục được mount vào backend tại `/remotelab/userdata`.

Khả năng cao đây là nơi lưu dữ liệu user hoặc workspace theo người dùng trong runtime.

### 9. `scripts/`

Chứa tài liệu hoặc script hỗ trợ ngoài code chính.

- `Bảng Kỹ Thuật API.xlsx`: tài liệu API dạng bảng

### 10. Tài liệu gốc ở thư mục root

- `README.md`: mô tả tổng quan project
- `map.md`: bản đồ cấu trúc thư mục này
- `API_DOCUMENTATION.md`: đặc tả API
- `PROJECT_OVERVIEW_VN.md`: tổng quan tiếng Việt
- `PHASE2_SUMMARY.md`: tóm tắt phase 2
- `TESTING_GUIDE.md`: hướng dẫn test
- `UI_ARCHITECTURE.md`: kiến trúc giao diện

## Nên tìm gì ở đâu

### Khi cần sửa API auth

Xem:

- `backend/app/routes/auth.py`
- `backend/app/auth_decorator.py`
- `frontend/src/store/authStore.ts`
- `frontend/src/api/client.ts`

### Khi cần sửa flash firmware

Xem:

- `frontend/src/components/FlashFirmwareModal.tsx`
- `frontend/src/api/index.ts`
- `backend/app/routes/hardware.py`
- `broker/app/main.py`
- `broker/app/protocol.py`

### Khi cần sửa lock/unlock thiết bị

Xem:

- `frontend/src/components/LockUnlockModal.tsx`
- `backend/app/routes/hardware.py`
- `backend/app/services/hardware_service.py`

### Khi cần sửa dashboard hoặc admin UI

Xem:

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/DeviceDetail.tsx`
- `frontend/src/pages/AdminPanel.tsx`
- `frontend/src/styles/`

### Khi cần sửa logic phát hiện thiết bị USB

Xem:

- `hardware_manager/listener.py`
- `backend/app/routes/internal.py`
- `backend/app/services/hardware_service.py`

## Thư mục nên bỏ qua khi đọc code

Khi review hoặc onboard vào project, bạn có thể bỏ qua trước:

- `frontend/node_modules/`
- `frontend/dist/`
- `backend/__pycache__/`
- `backend/app/__pycache__/`
- `backend/app/routes/__pycache__/`
- `backend/app/services/__pycache__/`
- `firmware/**/build/`

## Gợi ý mở rộng map sau này

Nếu project tiếp tục lớn hơn, có thể nâng cấp `map.md` theo hướng:

- thêm sơ đồ dependency giữa service
- thêm owner/module responsibility
- đánh dấu file entry point của từng service
- đánh dấu thư mục runtime và thư mục generated
