# PHASE 6 LITE — MASTER PLAN
# Remote Hardware Lab — Minimal-Risk Arduino Uno Integration and Targeted Stability Fixes
# Đọc file này TOÀN BỘ trước khi làm bất cứ việc gì.

---

## 1. SESSION START RULE

Trước khi làm bất cứ điều gì trong bất kỳ phiên làm việc nào:
1. Đọc toàn bộ file này.
2. Khôi phục ngữ cảnh từ file này — KHÔNG hỏi lại người dùng những gì đã có trong plan.
3. Coi kế hoạch này là đã được duyệt, trừ khi người dùng thay đổi phạm vi rõ ràng.
4. Bắt đầu từ task **chưa hoàn thành đầu tiên** trong checklist ở cuối file.
5. Cập nhật checklist sau mỗi task hoàn thành.
6. Nếu gặp blocker, dừng lại và báo cáo rõ trước khi mở rộng phạm vi.

---

## 2. MỤC TIÊU CỦA PHASE 6 LITE

Phase 6 Lite chỉ phục vụ đúng 3 mục tiêu:

1. **Fix các bug nhỏ nhưng đang ảnh hưởng trực tiếp đến device presence / disconnect reliability**
2. **Thêm một nút admin `Check` để hỗ trợ định danh thiết bị pending còn thiếu thông tin**
3. **Tích hợp Arduino Uno vào pipeline nạp firmware với mức thay đổi nhỏ nhất có thể**

Đây là phase **ít rủi ro**, **ít đụng logic**, **không mở rộng kiến trúc**.

---

## 3. CƠ SỞ CHỌN PHẠM VI (DỰA TRÊN REPO AUDIT)

Repo audit đã xác nhận:

- Project **đã có groundwork thật cho Arduino Uno**, đặc biệt ở compile-side `.hex` handling và board typing.
- Flash path hiện tại vẫn **ESP-only** trong queue / worker / broker.
- Có 3 bug runtime đã biết:
  1. `Unread result found` ở disconnect path
  2. stale `connected` state sau shutdown/restart đột ngột
  3. connect timeout quá ngắn gây race / port reuse / duplicate or stale state
- Các bug trên **có thể xử lý bằng patch nhỏ**, chưa cần refactor lớn.

---

## 4. NHỮNG GÌ ĐANG ỔN ĐỊNH VÀ PHẢI BẢO VỆ

Các phần sau được coi là baseline ổn định và **không được làm hỏng**:

- ESP32 compile → flash → serial → History
- ESP8266 compile → flash → serial → History
- Baud selector trong Flash Dialog
- FIFO queue + device lock/unlock
- Stop-live runtime termination
- Usage mode: `free / share / block`
- Pending review / approve / reset / delete
- Board-aware Flash Dialog filtering
- Admin metadata UI
- User-visible data minimization
- Workspace / editor / compile flow

---

## 5. HARD SCOPE

### ĐƯỢC LÀM
- Fix `Unread result found` ở disconnect path
- Tăng timeout connect event nếu cần
- Thêm reconcile tối thiểu lúc startup để clear stale `connected`
- Thêm admin action `Check` cho pending device
- Tích hợp Arduino Uno flash bằng `avrdude`
- Mở Uno ở Flash Dialog / workspace khi backend đã hỗ trợ đủ

### KHÔNG ĐƯỢC LÀM
- Không refactor toàn bộ queue
- Không refactor broker serial runtime chung
- Không đụng ping/pong / live-session extension
- Không redesign frontend rộng
- Không mở thêm cơ chế identity phức tạp ngoài mức tối thiểu
- Không tự động approve device
- Không tự động cấp quyền usable cho device mới

---

## 6. NGUYÊN TẮC THỰC THI

### 6.1 Ít thay đổi nhất có thể
- Tận dụng lại những gì repo đã có
- Nếu `.hex` compile đã chạy được thì **không sửa compile path**
- Chỉ thêm những mảnh còn thiếu để Uno flash được thật

### 6.2 Phân tách rõ hai thời điểm
- **Lúc cắm thiết bị**: bài toán nhận diện / enrich metadata
- **Lúc bấm Nạp**: bài toán chọn tool flash

### 6.3 Không ép mọi board dùng chung một logic probe
- ESP-class: có thể interrogate/probe theo đường ESP
- Arduino Uno: ưu tiên USB serial number, admin classify thủ công hoặc gợi ý
- Không dùng `esptool` để cố nhận diện Uno

### 6.4 Admin xác nhận cuối cùng
- Nút `Check` chỉ giúp đọc thêm thông tin và gợi ý
- Không auto-approve
- Không tự đổi usage_mode

---

## 7. BATCH 6L-A — STABILITY MICRO-FIXES

### Mục tiêu
Vá đúng các bug nhỏ đang cản trở định danh và quản lý thiết bị, theo cách hẹp nhất có thể.

### 6L-A.1 — Fix `Unread result found` ở disconnect path
**Phạm vi:**
- `backend/app/services/hardware_service.py`
- các helper liên quan trong disconnect/internal route nếu thật sự cần

**Yêu cầu:**
- rà mọi `cursor.execute()` có trả row
- bắt buộc `fetchone()` / `fetchall()` hết trước khi execute tiếp hoặc close
- cursor đóng trong `finally`
- retest: cắm → rút → HTTP 200, không còn 500

### 6L-A.2 — Tăng timeout connect event
**Phạm vi:**
- `hardware_manager/listener.py`

**Yêu cầu:**
- connect event timeout tăng từ 10s lên 30s
- disconnect timeout giữ ngắn như hiện tại nếu không cần đổi
- mục tiêu: absorb thời gian probe ESP (~10–15s), tránh race connect/disconnect

### 6L-A.3 — Startup reconcile tối thiểu
**Phạm vi:**
- một endpoint nội bộ rất nhỏ ở backend
- một lần gọi ở startup của hardware_manager

**Yêu cầu:**
- chỉ chạy **một lần khi startup**
- gửi danh sách port đang hiện diện thực tế
- backend query các row `status = connected`
- row nào không còn xuất hiện trong danh sách active port hiện tại thì:
  - `status = disconnected`
  - `port = NULL`
- **không** làm periodic heal
- **không** thêm cơ chế background mới
- **không** unlock hoặc đổi queue state
- mục tiêu duy nhất: clear stale `connected` sau crash/restart

### 6L-A.4 — Port safety tối thiểu
Nếu khi connect một device mới vào một `port` đang bị row khác giữ `connected`, backend được phép:
- clear row conflict cũ về `disconnected` + `port = NULL`
- nhưng chỉ khi identity không khớp

Không mở rộng thành identity framework mới trong phase này.

### Retest 6L-A tối thiểu
1. Cắm thiết bị → rút thiết bị → không còn `Unread result found`
2. Cắm một thiết bị duy nhất vào `/dev/ttyUSB0` → connect không timeout
3. Rút rồi cắm lại → không tạo row rác do race connect/disconnect
4. Shutdown đột ngột khi còn thiết bị cắm → khởi động lại → stale `connected` được clear
5. ESP32/ESP8266 flash + serial không regression

---

## 8. BATCH 6L-B — ADMIN `CHECK` / PROBE ASSIST

### Mục tiêu
Giúp admin chủ động đọc thêm thông tin cho pending devices đang thiếu metadata, thay vì nhìn card trống và phải đoán.

### UI
Trong Pending Review card, thêm nút:
- `Check`

### Backend
Thêm endpoint:
- `POST /api/admin/devices/<tag_name>/check`

### Hành vi
Khi admin bấm `Check`:
1. backend lấy row device hiện tại
2. nếu row có `serial_number` rõ ràng:
   - coi đây là strong hint cho USB-serial device kiểu Uno-like
   - có thể gợi ý `board_class = arduino_uno`
   - không gọi `esptool` chỉ để xác minh Uno
3. nếu row không có `serial_number`:
   - thử broker interrogate theo đường ESP
   - nếu probe được:
     - `chip_type`
     - `chip_family`
     - `mac_address`
     - `flash_size`
     - `crystal_freq`
   - điền các field còn thiếu vào DB
   - gợi ý `board_class = esp32` hoặc `esp8266`
4. nếu probe fail:
   - giữ trạng thái pending như cũ
   - hiển thị rõ là `Unknown / not supported for auto-detect`

### Ràng buộc
- Không auto-approve
- Không tự đổi usage_mode
- Không flash
- Chỉ enrich metadata + gợi ý admin chọn `board_class` / đặt tên

### Retest 6L-B tối thiểu
1. Pending device ESP thiếu metadata → bấm `Check` → metadata ESP được điền
2. Pending device Uno-like có serial → bấm `Check` → gợi ý `arduino_uno`
3. Admin vẫn sửa tay được `board_class`
4. Flow approve/classify cũ không regression

---

## 9. BATCH 6L-C — ARDUINO UNO MINIMAL FLASH SUPPORT

### Mục tiêu
Tích hợp Uno vào hệ thống với số thay đổi ít nhất, tận dụng compile `.hex` hiện có nếu repo/base image đã hỗ trợ.

### 6L-C.1 — Ưu tiên tận dụng compile hiện có
Trước khi thêm compile toolchain mới:
1. xác nhận compile `arduino_uno` hiện tại có ra `.hex` hay không
2. nếu **đã ra `.hex` ổn**:
   - không sửa compile path
3. chỉ nếu **không ra `.hex`**:
   - mới bổ sung toolchain/AVR core cần thiết

### 6L-C.2 — Queue file validation theo board
**Phạm vi:**
- `backend/app/services/flash_queue_service.py`

**Yêu cầu:**
- `esp32` / `esp8266` → chấp nhận `.bin`
- `arduino_uno` → chấp nhận `.hex`
- không dùng chung một rule `.bin-only`

### 6L-C.3 — Broker flash Uno bằng `avrdude`
**Phạm vi:**
- `broker/Dockerfile`
- `broker/app/main.py`

**Yêu cầu:**
- cài `avrdude`
- thêm đường flash cho `board = arduino_uno`
- command mẫu:
  - `avrdude -p atmega328p -c arduino -P /dev/ttyUSBx -b <baud> -U flash:w:firmware.hex:i`
- parse success/fail rõ ràng
- không đụng ESP flash path đang ổn

### 6L-C.4 — Worker routing theo board_class
**Phạm vi:**
- `backend/app/services/flash_queue_worker.py`

**Yêu cầu:**
- `board_type = arduino_uno` → route sang payload/logic Uno
- `board_type = esp32/esp8266` → giữ nguyên path hiện tại
- không ép Uno đi qua esptool

### 6L-C.5 — Flash Dialog / Workspace
**Phạm vi:**
- `frontend/src/pages/ProjectWorkspace.tsx`
- nếu cần, `frontend/src/components/FlashDialog.tsx`

**Yêu cầu:**
- bỏ chặn Uno là compile-only khi backend/broker đã hỗ trợ đủ
- khi chọn board `arduino_uno`, Flash Dialog chỉ hiện device `board_class = arduino_uno`
- dùng artifact `.hex`
- khi chọn ESP, không hiện Uno

### 6L-C.6 — Serial capture
Sau flash Uno thành công:
- serial capture như hiện tại
- không tạo runtime path mới
- không đụng broker serial logic chung ngoài chỗ cần thiết để Uno flash xong rồi serial đọc bình thường

### Retest 6L-C tối thiểu
1. Compile sketch Uno → có `.hex`
2. Flash `.hex` lên Uno → History `success`
3. Serial output Uno hiển thị đúng
4. Flash Dialog chọn Uno → chỉ hiện device Uno
5. Flash Dialog chọn ESP32 → không hiện Uno
6. ESP32/ESP8266 không regression

---

## 10. THỨ TỰ THỰC HIỆN BẮT BUỘC

```text
Step 1: Batch 6L-A.1 fix Unread result found
Step 2: Batch 6L-A.2 increase connect timeout
Step 3: Batch 6L-A.3 minimal startup reconcile
Step 4: Manual retest Batch 6L-A

[Chờ xác nhận thủ công]

Step 5: Batch 6L-B add admin Check / Probe assist
Step 6: Manual retest Batch 6L-B

[Chờ xác nhận thủ công]

Step 7: Batch 6L-C verify existing Uno .hex compile path
Step 8: Batch 6L-C add avrdude broker flash path
Step 9: Batch 6L-C add worker board-aware routing
Step 10: Batch 6L-C enable Uno in workspace / flash dialog
Step 11: Manual retest Batch 6L-C

[Chờ xác nhận thủ công]
```

---

## 11. BLOCKER POLICY

Nếu gặp blocker:
1. Dừng ngay, không mở rộng phạm vi.
2. Báo cáo:
   - blocker cụ thể
   - ảnh hưởng
   - bước an toàn nhất tiếp theo
3. Chờ duyệt trước khi đổi kiến trúc.

Không bịa identity, không bịa auto-detect, không bịa Uno support nếu compile/flash chưa test thật.

---

## 12. OUTPUT DISCIPLINE

- Response ngắn gọn, có cấu trúc.
- Không claim “đã hỗ trợ Uno” nếu chưa flash thật.
- Nếu phải thêm package vào container: nói rõ container nào và lệnh rebuild.
- Nếu phải thêm migration DB: nêu SQL cụ thể.
- Không gộp nhiều giả thuyết vào một patch.

---

## 13. TASK CHECKLIST
> `[ ]` Chưa bắt đầu | `[~]` Đang làm | `[x]` Xong | `[!]` Blocked

### Batch 6L-A — Stability micro-fixes
- [x] Trace disconnect path và mọi cursor usage liên quan
- [x] Fix `Unread result found`
- [x] Tăng connect timeout lên 30s
- [x] Thêm startup reconcile tối thiểu
- [x] Retest: cắm/rút sạch, không còn 500
- [x] Retest: shutdown/restart clear được stale connected
- [x] Non-regression: ESP32/ESP8266 flash + serial vẫn OK
- [x] Manual retest Batch 6L-A completed

### Batch 6L-B — Admin Check / Probe assist
- [x] Thêm admin endpoint `POST /api/admin/devices/<tag_name>/check`
- [x] Thêm nút `Check` trong Pending Review
- [x] ESP pending device có thể enrich metadata bằng probe
- [x] Uno-like device có thể được gợi ý `arduino_uno`
- [x] Admin vẫn sửa tay / approve như cũ
- [x] Manual retest Batch 6L-B completed

### Batch 6L-C — Arduino Uno minimal support
- [x] Xác nhận compile `.hex` hiện có dùng được hay không
- [x] Thêm `avrdude` vào broker nếu cần
- [x] Queue validation chấp nhận `.hex` cho `arduino_uno`
- [x] Broker có Uno flash path
- [x] Worker route `arduino_uno` đúng
- [x] Workspace / Flash Dialog cho phép Uno flash
- [ ] Serial capture Uno hoạt động
- [ ] Non-regression: ESP32/ESP8266 không bị ảnh hưởng
- [ ] Manual retest Batch 6L-C completed

---

*Last updated: 2026-04-19*
*Dựa trên: Phase-5-master-plan.md + Phase-6-master-plan.md + repo audit trước Phase 6 Lite*
