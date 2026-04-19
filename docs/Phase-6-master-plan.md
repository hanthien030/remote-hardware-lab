# PHASE 6 — MASTER PLAN
# Remote Hardware Lab — Stability Hardening, Stale State Recovery, and Arduino Uno Support
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

## 2. TRẠNG THÁI DỰ ÁN TRƯỚC KHI BẮT ĐẦU PHASE 6

### 2.1 Những gì đang ổn định và phải bảo vệ

- ESP32 compile → flash → serial log → History ✅
- ESP8266 compile → flash → serial log → History ✅
- Baud selector trong Flash Dialog ✅
- Single-open serial capture (không còn segment loop) ✅
- FIFO queue + device lock/unlock ✅
- Session/auth ✅
- Usage mode: `free / share / block` ✅
- Pending review + auto board-class detection (5A) ✅
- Admin metadata UI (5B) ✅
- User-visible data minimization (5C) ✅
- Workspace / editor / compile flow ✅

### 2.2 Bugs đã xác nhận cần fix

#### Bug 1 — "Unread result found" khi disconnect
**Triệu chứng:**
```
ERROR - Lỗi HTTP (500): {"error": "Internal server error: Unread result found"}
```
**Khi nào xảy ra:** Hardware manager báo disconnect → backend xử lý → MySQL cursor bị unread result → 500.
**Root cause:** Trong `handle_device_disconnect()` hoặc hàm liên quan, có cursor chưa `fetchone()`/`fetchall()` hết result trước khi execute lệnh khác hoặc đóng cursor.

#### Bug 2 — Stale "connected" state sau khi hệ thống tắt đột ngột
**Triệu chứng:**
- Tắt máy ảo/server đột ngột (không rút thiết bị trước).
- Khởi động lại → DB vẫn giữ `status = connected` cho device đã mất.
- Device bị phantom connected: không thể dùng, không thể unlock.

#### Bug 3 — Port collision khi chỉ có 1 thiết bị tại một thời điểm
**Triệu chứng:**
- Thiết bị cắm vào `/dev/ttyUSB0`, backend timeout (esptool probe mất ~15s, timeout chỉ 10s) → disconnect event gửi trước khi connect xử lý xong → port bị giữ trong DB.
- Cắm thiết bị khác vào → cùng port → conflict hoặc tạo duplicate row.
- Chỉ hết bug khi cắm 2 thiết bị cùng lúc để OS phân port khác nhau.

**Root cause:** Timeout HTTP cho connect event (10s) quá ngắn so với thời gian probe (~15s).

### 2.3 Tính năng mới

#### Feature — Arduino Uno compile + flash support
- `esptool` chỉ dùng được cho ESP32/ESP8266.
- Arduino Uno cần `avrdude` để flash và `arduino-cli` hoặc `avr-gcc` để compile.
- Hệ thống phải phân biệt đường flash theo `board_class`.
- Serial capture sau flash Arduino Uno dùng pyserial như bình thường.

---

## 3. HARD SCOPE

### ĐƯỢC LÀM
- Fix Bug 1, 2, 3
- Thêm Arduino Uno compile + flash pipeline
- Startup reconciliation để heal stale state
- Cải thiện disconnect reliability

### KHÔNG ĐƯỢC LÀM
- Không refactor toàn bộ queue/flash logic
- Không đụng Virtualized / MPU / multi-slot
- Không redesign frontend ngoài phần liên quan Arduino Uno
- Không làm hỏng ESP32/ESP8266 pipeline đang ổn
- Không tự động approve device

---

## 4. BLOCKER POLICY

Nếu gặp blocker:
1. Dừng ngay, không mở rộng phạm vi.
2. Báo cáo: blocker cụ thể, ảnh hưởng, bước an toàn nhất.
3. Chờ duyệt trước khi thay đổi kiến trúc lớn.

---

## 5. BATCH 6A — STABILITY FIXES

### Ưu tiên: CRITICAL — phải xong và pass trước khi làm Batch 6B.

---

### Fix 1 — Unread result found trong disconnect handler

**File:** `backend/app/services/hardware_service.py`

**Hướng fix:**
- Đọc toàn bộ `handle_device_disconnect()` và tất cả hàm nó gọi.
- Tìm mọi chỗ `cursor.execute()` mà sau đó không có `fetchone()` / `fetchall()` trước khi execute tiếp hoặc đóng cursor.
- Đảm bảo mọi SELECT đều được fetch hết trước khi chuyển sang lệnh khác.
- Đảm bảo cursor luôn được đóng trong `finally`.

Pattern an toàn bắt buộc:
```python
cursor.execute("SELECT ...")
row = cursor.fetchone()  # bắt buộc — dù không dùng row
# rồi mới execute tiếp hoặc close
```

**Retest:** Cắm thiết bị → rút ra → `docker logs backend_service` không còn "Unread result found", HTTP 200.

---

### Fix 2 — Startup reconciliation

**Vấn đề:** Khi backend/hardware_manager khởi động lại sau crash, DB có thể chứa device với `status = connected` nhưng thực tế đã bị rút.

**Hướng fix:**

Khi hardware_manager khởi động (`main_loop()` bắt đầu):
1. Lấy danh sách port thực tế đang cắm (`list_ports.comports()`).
2. Gọi endpoint mới: `POST /api/internal/hardware/reconcile`.
3. Backend nhận danh sách port → query DB tìm tất cả device `status = connected` → so sánh → device không còn trong danh sách thực tế → set `status = disconnected`, `port = NULL`.

**API mới:**
```
POST /api/internal/hardware/reconcile
Header: X-Internal-API-Key: ...
Body: { "active_ports": ["/dev/ttyUSB0", "/dev/ttyUSB1"] }
Response: { "reconciled": 2, "stale_cleared": 1 }
```

**Ràng buộc:**
- Chỉ gọi reconcile một lần khi startup, không gọi định kỳ.
- Không tự unlock device đang bị lock bởi flash job — chỉ clear `status`.
- Nếu backend chưa ready → retry với backoff tối đa 3 lần, rồi tiếp tục bình thường (không crash).

**Retest:**
1. Cắm thiết bị → tắt hệ thống đột ngột (không rút thiết bị).
2. Rút thiết bị khi hệ thống đang tắt.
3. Khởi động lại.
4. DB: device phải ở `status = disconnected`.

---

### Fix 3 — Disconnect timeout + port collision

**Hướng fix — chỉ sửa `hardware_manager/listener.py`:**

Tăng timeout của HTTP request cho event `connect` lên 30 giây:

```python
# Trước:
response = requests.post(endpoint, json=payload, headers=headers, timeout=10)

# Sau:
connect_timeout = 30 if event_type == 'connect' else 10
response = requests.post(endpoint, json=payload, headers=headers, timeout=connect_timeout)
```

**Lý do:** Probe `esptool flash-id` mất ~10-15s. Timeout 10s quá ngắn → request bị cut → backend chưa kịp ghi DB → disconnect event đến trước → DB sai.

**Retest:**
1. Cắm thiết bị duy nhất vào `/dev/ttyUSB0` → hardware_manager không timeout → backend xử lý thành công.
2. Rút thiết bị → disconnect HTTP 200.
3. Cắm lại → nhận dạng đúng device cũ (match by MAC hoặc serial_number), không tạo row mới.

---

## 6. BATCH 6B — ARDUINO UNO SUPPORT

### Ưu tiên: HIGH — sau khi Batch 6A pass.

---

### 6.1 Tổng quan pipeline

| | ESP32 | ESP8266 | Arduino Uno |
|--|--|--|--|
| Compile tool | arduino-cli / esp-idf | arduino-cli | arduino-cli / avr-gcc |
| Flash tool | esptool | esptool | avrdude |
| Output format | .bin | .bin | .hex |
| Serial capture | pyserial (dtr=False) | pyserial (dtr=False) | pyserial (dtr=False) |
| Auto-probe | esptool flash-id | esptool flash-id | Không hỗ trợ (admin classify thủ công) |

---

### 6.2 Infrastructure — Container

**Cần thêm vào broker container (`broker/Dockerfile`):**
```dockerfile
RUN apt-get update && apt-get install -y avrdude && rm -rf /var/lib/apt/lists/*
```

**Cần thêm vào compiler/backend container (tùy cấu trúc project):**
- `arduino-cli` nếu dùng để compile Arduino Uno
- Hoặc `avr-gcc` + `avr-objcopy` nếu dùng toolchain thủ công

Kiểm tra container nào đang xử lý compile trước khi thêm package.

---

### 6.3 Compile pipeline

**Yêu cầu:**
- Board selector "Arduino Uno" trong editor → compile backend chọn đúng toolchain.
- Output: file `.hex` (Intel HEX format).
- Lưu `.hex` vào workspace sau compile thành công.
- Log compile hiện trong output panel như bình thường.

**Lưu ý:** Không dùng `.bin` cho Arduino Uno. `avrdude` cần `.hex`.

---

### 6.4 Flash pipeline

**Broker — thêm endpoint hoặc logic avrdude:**

Command mẫu:
```bash
avrdude -p atmega328p -c arduino -P /dev/ttyUSB0 -b 115200 -U flash:w:sketch.hex:i
```

Parse output để detect:
- Success: `avrdude: N bytes of flash verified`
- Fail: `avrdude: error` hoặc exit code != 0

Timeout: 60s.

**Worker — routing theo board_type:**
```python
if request_row['board_type'] == 'arduino_uno':
    # gọi avrdude path
    broker_payload = {
        'port': device['port'],
        'firmware_hex_base64': ...,  # base64 của file .hex
        'board': 'arduino_uno',
    }
else:
    # giữ nguyên esptool path hiện tại
```

**Ràng buộc:**
- Không thay đổi ESP32/ESP8266 flash path.
- `flash_layout` chỉ dùng cho ESP32, không áp dụng cho Arduino Uno.

---

### 6.5 Serial capture

- Sau khi flash Arduino Uno thành công → serial capture như bình thường.
- `dtr=False`, `rts=False` sau khi mở port — đã có sẵn từ fix Phase 4.
- Baud rate do user chọn trong Flash Dialog (baud selector đã có sẵn).

---

### 6.6 Probe/Identify Arduino Uno

- Arduino Uno có USB serial number cố định → hardware_manager gửi `serial_number` → backend nhận dạng được.
- Không gọi `esptool` cho Arduino Uno → probe sẽ fail gracefully → `board_class = NULL` → admin classify thủ công.
- Phase 6 **không yêu cầu** auto-detect Arduino Uno — chấp nhận admin classify thủ công là đủ.

---

### 6.7 Flash Dialog

- Khi user chọn board "Arduino Uno":
  - Chỉ hiển thị device có `board_class = arduino_uno`, đang connected, đúng usage_mode.
  - Firmware phải là file `.hex`.
- Compile output `.hex` phải được Flash Dialog nhận diện đúng.

---

## 7. THỨ TỰ THỰC HIỆN BẮT BUỘC

```
Batch 6A:
  Bước 1: Fix Bug 1 (Unread result found — hardware_service.py)
  Bước 2: Fix Bug 2 (Startup reconciliation — listener.py + backend route mới)
  Bước 3: Fix Bug 3 (Timeout connect event — listener.py)
  Bước 4: Manual retest Batch 6A

[Chờ xác nhận thủ công]

Batch 6B:
  Bước 5: Thêm avrdude vào broker container
  Bước 6: Compile pipeline cho Arduino Uno (.hex output)
  Bước 7: Broker: avrdude flash logic
  Bước 8: Worker: routing arduino_uno → avrdude path
  Bước 9: Flash Dialog filter arduino_uno
  Bước 10: Manual retest Batch 6B toàn diện

[Chờ xác nhận thủ công]
```

---

## 8. RETEST EXPECTATIONS

### Retest Batch 6A (tối thiểu)

1. Cắm thiết bị → rút ra → `docker logs backend_service` không còn "Unread result found". HTTP 200.
2. Tắt hệ thống đột ngột khi thiết bị đang cắm → rút thiết bị → khởi động lại → DB: `status = disconnected`.
3. Cắm thiết bị duy nhất vào USB0 → connect thành công (không timeout) → rút → disconnect thành công → cắm lại → nhận dạng đúng device cũ.
4. ESP32/ESP8266 flash + serial vẫn hoạt động bình thường (non-regression).

### Retest Batch 6B (tối thiểu)

1. Compile sketch Arduino Uno → file `.hex` xuất hiện trong workspace.
2. Flash `.hex` lên Arduino Uno → History hiện `success`.
3. Serial output từ Arduino Uno hiển thị đúng trong History.
4. Flash Dialog chọn "Arduino Uno" → chỉ hiện device `board_class = arduino_uno`.
5. Flash Dialog chọn "ESP32" → không hiện Arduino Uno.
6. ESP32/ESP8266 flash + serial không bị ảnh hưởng (non-regression).

---

## 9. BÀI HỌC TỪ CÁC PHASE TRƯỚC (BẮT BUỘC NHỚ)

- **Không đụng broker serial runtime chung** trước khi có evidence rõ ràng.
- **Patch nhỏ, từng bước, retest ESP32/ESP8266 ngay** sau mỗi thay đổi broker.
- **Tách biệt rõ** đường ESP và đường Arduino — không dùng chung logic nếu bản chất khác nhau.
- **Cursor MySQL phải fetchall/fetchone hết** trước khi execute lệnh tiếp hoặc close.
- **Timeout HTTP cho connect event phải đủ dài** để chứa thời gian probe (~15s).
- **Không gộp nhiều giả thuyết** vào một lần patch.

---

## 10. OUTPUT DISCIPLINE

- Response ngắn gọn, có cấu trúc.
- Không nói "đã xác nhận" nếu chưa test thật.
- Nếu cần thêm package vào container: nêu rõ container nào, Dockerfile thay đổi gì.
- Nếu cần migration DB: cung cấp SQL cụ thể.
- Nếu cần rebuild container: nói rõ lệnh.

---

## 11. TASK CHECKLIST
> `[ ]` Chưa bắt đầu | `[~]` Đang làm | `[x]` Xong | `[!]` Blocked

### Batch 6A — Stability Fixes

#### Fix 1 — Unread result found
- [ ] Trace `handle_device_disconnect()` và tất cả cursor usage liên quan
- [ ] Fix cursor lifecycle (fetchone/fetchall trước khi execute tiếp hoặc close)
- [ ] Retest: rút thiết bị → HTTP 200, không còn 500

#### Fix 2 — Startup reconciliation
- [ ] Thêm `POST /api/internal/hardware/reconcile` vào backend
- [ ] Thêm reconcile call vào hardware_manager khi startup (với retry backoff)
- [ ] Retest: shutdown đột ngột → khởi động lại → stale state được clear

#### Fix 3 — Disconnect timeout
- [ ] Tăng timeout connect event lên 30s trong `listener.py`
- [ ] Retest: cắm thiết bị duy nhất → không timeout → không tạo duplicate row

#### Batch 6A wrap-up
- [ ] Non-regression: ESP32/ESP8266 flash + serial vẫn OK
- [ ] Manual retest Batch 6A completed

---

### Batch 6B — Arduino Uno Support

#### Infrastructure
- [ ] Xác định container nào cần avrdude
- [ ] Thêm avrdude vào broker Dockerfile + rebuild
- [ ] Xác định container nào cần arduino-cli / avr-gcc cho compile
- [ ] Thêm toolchain compile + rebuild

#### Compile pipeline
- [ ] Compile backend xử lý Arduino Uno → output `.hex`
- [ ] File `.hex` lưu vào workspace

#### Flash pipeline
- [ ] Broker: thêm avrdude flash logic
- [ ] Worker: routing `board_type = arduino_uno` → avrdude path
- [ ] Parse avrdude output để detect success/fail

#### Serial capture
- [ ] Verify serial capture hoạt động cho Arduino Uno
- [ ] Test với baud 9600 và 115200

#### Flash Dialog
- [ ] Filter device theo `board_class = arduino_uno` khi chọn Arduino Uno
- [ ] Firmware selector chấp nhận `.hex` cho Arduino Uno

#### Batch 6B wrap-up
- [ ] Non-regression: ESP32/ESP8266 không bị ảnh hưởng
- [ ] Manual retest Batch 6B completed

---

*Last updated: 2026-04-19*
*Dựa trên: Phase-4-master-plan.md + Phase-5-master-plan.md + bugs phát hiện sau Phase 5*
