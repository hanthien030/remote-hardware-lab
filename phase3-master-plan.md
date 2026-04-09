# PHASE 3 — MASTER PLAN
# Remote Hardware Lab — Redesign & Feature Completion
# Được viết tay bởi tác giả từ 3h–7h sáng. KHÔNG SKIP.

---

## TỔNG QUAN KIẾN TRÚC MỚI

### Thay đổi lớn so với hiện tại
1. Bỏ cơ chế Lock/Unlock thủ công → thay bằng FIFO Queue tự động
2. Bỏ luồng "bấm vào device mới vào code" → workspace độc lập với device
3. Tách Compile và Flash thành 2 bước riêng biệt
4. Sidebar navigation thay cho layout hiện tại
5. Real-time updates qua WebSocket (không cần F5)
6. Admin: 3 trạng thái thiết bị Free/Block/Share thay cho Assign đơn giản

---

## PHASE 3A — NỀN TẢNG (Làm trước, mọi thứ phụ thuộc vào đây)
### Ưu tiên: CRITICAL

### 3A-1: WebSocket real-time (2 ngày)
**Vấn đề:** Cắm/rút ESP32 phải F5 mới cập nhật
**Giải pháp:** WebSocket server trong backend, broadcast sự kiện
- Backend: thêm WebSocket endpoint `/ws`
- hardware_manager gửi event → backend broadcast → frontend nhận
- Frontend: update device status tự động không cần reload
- Events cần handle: device_connected, device_disconnected, 
  device_locked, device_unlocked, flash_started, flash_done

### 3A-2: Sidebar Navigation (1 ngày)
**Cấu trúc Sidebar (User):**
```
[≡] Logo
────────────
[💻] Làm việc    ← workspace, mặc định sau login
[📋] Thiết bị    ← danh sách free + được share
[📜] Lịch sử     ← log các phiên nạp
[👤] Cá nhân     ← thông tin tài khoản (ưu tiên thấp)
────────────
[🚪] Đăng xuất
```
**Cấu trúc Sidebar (Admin):**
```
[≡] Logo
────────────
[🔧] Thiết bị    ← quản lý device (ưu tiên cao)
[👥] Người dùng  ← quản lý user
────────────
[🚪] Đăng xuất
```
**Hành vi:** 
- Sidebar thu lại khi vào giao diện Làm việc
- Bấm icon ≡ để mở/đóng
- Tự động redirect đúng dashboard sau login (admin→admin, user→workspace)

### 3A-3: Project System (1 ngày)
**Khái niệm:** Workspace = thư mục `/workspaces/{username}/`
**Project** = thư mục con `/workspaces/{username}/{project_name}/`
- API: GET/POST/DELETE /api/workspace/projects
- Vào giao diện Làm việc lần đầu: trống, có nút "+ Tạo dự án mới"
- Nhập tên dự án → tạo thư mục → vào ngay dự án đó
- Góc trên cùng có dropdown chuyển qua lại giữa các dự án

---

## PHASE 3B — FILE MANAGER & EDITOR (Làm sau 3A)
### Ưu tiên: HIGH

### 3B-1: File Manager đầy đủ như VSCode (3 ngày)
**Chuột phải vào thư mục:**
- New File, New Folder, Rename, Delete, 

**Chuột phải vào file:**
- Open, Rename, Delete, Copy, Cut, Paste

**Kéo thả:**
- Giữ chuột trái kéo file/folder vào thư mục khác

**Phím tắt:**
- Ctrl+S: lưu file đang mở
- Ctrl+Z: undo trong editor
- F2: rename item đang chọn
- Delete: xóa item đang chọn

**Thông báo mọi thao tác:**
- Toast nhỏ góc màn hình: "Đã tạo file main.cpp", "Đã xóa test.cpp"...
- Log hoạt động lưu vào DB (dùng cho quản lý online/offline sau)

**Định dạng file hỗ trợ:**
- .cpp, .c, .h, .ino, .py, .txt, .json, .md
- Bấm vào file → mở trong Monaco với syntax highlight đúng loại

### 3B-2: Multi-tab Monaco Editor (1 ngày)
- Mở nhiều file cùng lúc, mỗi file 1 tab
- Tab có nút X để đóng
- Tab có dấu • nếu chưa lưu (unsaved)
- Ctrl+S lưu tab đang active
- Auto-save sau 3 giây không gõ phím

### 3B-3: Compile độc lập (1 ngày)
**Nút [🔨 Biên dịch]** trong footer editor, luôn hiển thị
- KHÔNG cần thiết bị
- KHÔNG cần lock
- Gọi compiler service với board type được chọn
- Output panel hiện log biên dịch realtime qua SSE
- Thành công: hiện ✅, lưu file .bin vào workspace
- Lỗi: hiện ❌ + highlight dòng lỗi trong editor (nếu có thể)

**Chọn board để compile:**
- Dropdown cạnh nút Biên dịch: ESP32 / ESP8266 / Arduino Uno
- Lưu lại lựa chọn cuối cùng của user

**Dọn file rác:**
- Sau compile: chỉ giữ lại file .bin cuối cùng
- Xóa: .elf, .map, build/core/*, build/libraries/* 
- Giữ: build/{project}.bin (cần để flash)

---

## PHASE 3C — FIFO QUEUE & FLASH SYSTEM (Làm sau 3B)
### Ưu tiên: HIGH — Đây là tính năng cốt lõi của đề tài

### Thiết kế Queue

**Nguyên tắc:**
- Mỗi thiết bị có 1 hàng đợi riêng
- Mỗi user chỉ được có 1 yêu cầu nạp pending tại 1 thời điểm
- User gửi xong có thể làm việc khác, system tự xử lý
- Giống đặt hàng online: đặt xong shipper lo, mình làm việc khác

**Schema DB mới cần thêm:**
```sql
CREATE TABLE flash_queue (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(50) NOT NULL,
  tag_name VARCHAR(50) NOT NULL,         -- thiết bị yêu cầu
  board_type VARCHAR(20) NOT NULL,       -- esp32/esp8266/arduino_uno
  firmware_path VARCHAR(255) NOT NULL,   -- đường dẫn file .bin
  status ENUM('waiting','flashing','success','failed','cancelled'),
  created_at DATETIME DEFAULT NOW(),
  started_at DATETIME,
  completed_at DATETIME,
  log_output TEXT,                       -- log từ esptool
  serial_log TEXT                        -- log từ serial monitor 1 phút
);
```

### 3C-1: Flash Dialog (1 ngày)
**Khi bấm [⚡ Nạp]** (chỉ hiện sau khi compile thành công):
Dialog box hiện ra với:
1. **Chọn Board:** ESP32 / ESP8266 / Arduino Uno (radio buttons)
2. **Chọn thiết bị:** 
   - Dropdown hiện danh sách device người dùng có quyền dùng (free + share)
   - Chỉ hiện device đang connected
   - Hiện trạng thái: 🟢 Rảnh / 🔴 Đang dùng (số người trong queue)
3. Nút **[Trở về]** và **[⚡ Gửi yêu cầu nạp]**

**Sau khi bấm Gửi:**
- Tự động chuyển qua tab Lịch sử
- Nút Nạp đổi thành **[⬛ HỦY]** màu đỏ
- Toast: "Đã gửi yêu cầu nạp, đang chờ thiết bị rảnh..."

### 3C-2: Queue Worker Backend (2 ngày)
**Background worker** chạy mỗi 2 giây:
```
Lấy tất cả request status='waiting'
Với mỗi device:
  Nếu device không bị lock và connected:
    Lấy request đầu tiên trong queue (FIFO - theo created_at)
    → Lock device cho user đó
    → Đổi status → 'flashing'
    → Gọi broker flash
    → Lưu log
    → Giữ lock 60 giây (serial logging)
    → Sau 60s: unlock, status → 'success'/'failed'
    → Notify user qua WebSocket
```

**Xử lý edge cases:**
- User hủy (bấm STOP): xóa khỏi queue, nếu đang flash thì abort
- Device ngắt kết nối đang flash: status → 'failed', unlock, notify
- User offline khi đang xem serial: auto-unlock sau 60s không có activity

### 3C-3: Serial Monitor (1 ngày)
**Sau khi flash thành công:**
- Backend tự động connect serial port của device 60 giây
- Stream data về cho user qua WebSocket
- Hiển thị trong tab Lịch sử, section "Serial Output"
- Auto-save toàn bộ vào `serial_log` trong DB

**Khi user muốn xem realtime:**
- Bấm vào flash record trong Lịch sử
- Nếu đang trong 60s lock: thấy serial stream trực tiếp
- Ping/pong mỗi 2 phút để verify user còn online
  - Server gửi: "Bạn có còn ở đây không? [✓ Có] [⏱ 10s]"
  - User không bấm trong 10s: disconnect, auto-unlock
  - User mất mạng: detect timeout WebSocket → auto-unlock

### 3C-4: Giao diện Lịch sử (1 ngày)
**Danh sách tất cả flash requests của user:**
- Thời gian, thiết bị, board, status, thời gian xử lý
- Bấm vào xem chi tiết: compile log + flash log + serial log
- Phân trang, filter theo status

**Yêu cầu nạp đang active (ở đầu list):**
- Hiện trạng thái realtime: ⏳ Đang chờ (vị trí X trong queue) / 🔄 Đang nạp... / ✅ Xong
- Nút [⬛ HỦY] nếu status = 'waiting'
- Progress bar nếu status = 'flashing'

---

## PHASE 3D — ADMIN REDESIGN (Có thể làm song song với 3C)
### Ưu tiên: MEDIUM

### 3D-1: Trạng thái thiết bị (1 ngày)
**3 trạng thái sử dụng** (khác với trạng thái kết nối connected/disconnected):
- **Free** 🟢: Tất cả user đều dùng được, không cần cấp phép
- **Share** 🔵: Chỉ user được admin cấp phép mới dùng được  
- **Block** 🔴: Không ai dùng được (bảo trì, hỏng...)

**Schema thêm vào bảng devices:**
```sql
ALTER TABLE devices ADD COLUMN usage_mode ENUM('free','share','block') DEFAULT 'free';
```

### 3D-2: Giao diện Thiết bị Admin (2 ngày)
**Mỗi device row có:**
- Thông tin: Tag Name, Type, Port, Status kết nối, Usage Mode
- Nút **[✏️ Sửa thông tin]**: sửa device_name, mô tả
- Dropdown **[Free / Share / Block]**: đổi usage_mode
- Nút **[👥 Quản lý Share]**: mở panel bên cạnh

**Panel Share (khi device ở chế độ Share):**
- Danh sách user đang được share: tên, email, hết hạn lúc
- Nút **[+ Thêm]**: nhập email → tìm user → hiện info → chọn thời hạn → confirm
- Nút **[🗑️ Xóa]** trên mỗi user: revoke ngay lập tức
- Một thiết bị share được cho bao nhiêu user cũng được

**Lưu ý quan trọng:**
- Queue system cần check usage_mode khi user gửi flash request
- Free: user nào có quyền dùng luôn
- Share: chỉ user trong danh sách share mới được gửi request
- Block: không ai gửi được

---

## DEPENDENCIES (thứ tự bắt buộc)

```
3A-1 (WebSocket) ──────────────────────────────► 3C-2 (Queue Worker)
3A-2 (Sidebar) ────────────────────────────────► 3C-4 (Lịch sử UI)  
3A-3 (Project System) ─► 3B-1 (File Manager) ─► 3B-3 (Compile)
                                                       │
                                                       ▼
                                                  3C-1 (Flash Dialog)
                                                       │
                                                       ▼
                                                  3C-3 (Serial Monitor)
```

---

## TASK CHECKLIST (Antigravity dùng file này để track)

### Phase 3A — Nền tảng
- [x] 3A-1: WebSocket server trong backend
- [x] 3A-1: WebSocket client trong frontend, auto-update device status
- [x] 3A-2: Sidebar component với navigation
- [x] 3A-2: Auto-redirect sau login (admin/user)
- [x] 3A-2: Sidebar thu lại khi vào workspace
- [x] 3A-3: Project API (CRUD)
- [x] 3A-3: Project UI (tạo, chọn, xóa dự án)

### Phase 3B — File Manager & Editor
- [x] 3B-0: VSCode-like Theme (chuẩn bị)
- [x] 3B-1: Context menu chuột phải cho thư mục
- [x] 3B-1: Context menu chuột phải cho file (copy/cut/paste)
- [x] 3B-1: Kéo thả file/folder
- [x] 3B-1: Phím tắt Ctrl+S, F2, Delete
- [x] 3B-1: Toast notification mọi thao tác
- [x] 3B-1: Hỗ trợ đa định dạng file
- [x] 3B-2: Multi-tab Monaco
- [x] 3B-2: Unsaved indicator (dấu •)
- [x] 3B-3: Nút Compile độc lập
- [x] 3B-3: Board selector dropdown
- [x] 3B-3: SSE compile log output panel
- [x] 3B-3: Highlight lỗi trong editor
- [x]  3B-3: Dọn file rác sau compile

### Phase 3C — Queue & Flash
- [x] 3C-0: Tạo bảng flash_queue trong DB
- [x] 3C-1: Flash Dialog UI
- [x] 3C-2: Queue worker backend
- [x] 3C-2: WebSocket notify khi flash done
- [x] 3C-2: Auto serial logging 60 giây
- [x] 3C-2: Auto unlock sau 60s
- [x] 3C-3: Serial monitor UI realtime
- [x] 3C-3: Ping/pong online detection
- [x] 3C-3: Auto-unlock khi offline/không response
- [x] 3C-4: Lịch sử UI với realtime status

### Phase 3D — Admin
- [x] 3D-1: Thêm usage_mode vào devices table
- [x] 3D-2: Admin device UI với 3 trạng thái
- [x] 3D-2: Share management panel
- [x] 3D-2: Queue check usage_mode khi nhận request

---
~
## GHI CHÚ THÊM
- "Invalid Date" bug trong device list: fix luôn khi đụng vào
- Truy cập từ IP 192.168.x.x lỗi: do VITE_API_URL hardcode localhost,
  cần dùng window.location.hostname thay vì hardcode
- Container per-user (remotelab_user_testuser): giữ nguyên thiết kế này