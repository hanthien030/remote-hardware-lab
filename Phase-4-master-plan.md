# PHASE 4 — MASTER PLAN
# Remote Hardware Lab — Bug Fixes & Board Classification
# Đọc file này TOÀN BỘ trước khi làm bất cứ việc gì.

---

## 1. SESSION START RULE

Trước khi làm bất cứ điều gì trong bất kỳ phiên làm việc nào:
1. Đọc toàn bộ file này.
2. Khôi phục ngữ cảnh từ file này — KHÔNG hỏi lại người dùng.
3. Coi kế hoạch này là đã được duyệt, trừ khi người dùng thay đổi phạm vi rõ ràng.
4. Bắt đầu từ task **chưa hoàn thành đầu tiên** trong checklist ở cuối file.
5. Cập nhật checklist sau mỗi task hoàn thành.
6. Nếu gặp blocker, dừng lại và báo cáo rõ trước khi mở rộng phạm vi.

---

## 2. TRẠNG THÁI DỰ ÁN HIỆN TẠI

### 2.1 Nền tảng ổn định (đã hoàn thành — bảo vệ, không được chạm vào)

Phase 3 đã hoàn tất toàn bộ. Những phần sau đang hoạt động tốt:

- **WebSocket real-time**: device connect/disconnect, flash events.
- **Sidebar navigation**: User (Làm việc / Thiết bị / Lịch sử) và Admin (Thiết bị / Người dùng).
- **Project system**: CRUD workspace/project theo từng user.
- **File Manager**: context menu, kéo thả, phím tắt, toast notification.
- **Multi-tab Monaco Editor**: unsaved indicator, auto-save.
- **Compile độc lập**: board selector, SSE log, highlight lỗi, dọn file rác.
- **Flash Dialog**: chọn board, chọn thiết bị, gửi yêu cầu nạp.
- **FIFO Queue Worker**: lock device, flash, serial 60s, unlock, notify.
- **Serial Monitor UI**: realtime stream, ping/pong, auto-unlock khi offline.
- **History UI**: realtime status, chi tiết flash log + serial log.
- **Admin Device UI**: usage_mode (free/share/block), share management panel.
- **ESP32 compile → flash → serial log → History**: hoạt động tốt.
- **Luồng FIFO queue**: đúng thứ tự, không bị tranh chấp.
- **Session/auth**: đã ổn định.
- **Stop-live control**: tồn tại và hoạt động cơ bản.

### 2.2 Các lỗi đã xác nhận cần sửa

#### Bug A — ESP8266 serial output không được lưu vào History
- Flash thành công.
- Sketch chạy thật (xác nhận bằng Arduino IDE: nhận đúng `ESP8266: LED ON / OFF`).
- Hệ thống KHÔNG ghi lại serial log, `serial_log` trống hoặc không hiển thị trong History.
- **Root cause chưa xác định** — cần điều tra bằng evidence trước khi patch.

#### Bug B — Manual stop đánh sai trạng thái `failed`
- Flash thành công.
- Serial stream hiển thị đúng dữ liệu.
- User nhấn stop sớm (đã xem đủ).
- History hiển thị `FAILED` thay vì `success`.
- Log có dòng: `"Serial capture interrupted before the live session could finish."`
- **Root cause**: worker state machine map manual stop → `interrupted` → `failed`.

### 2.3 Tính năng thiếu cần bổ sung

#### Feature C — Baud rate selector cho phiên nạp
- Hiện tại baud rate bị hardcode trong broker.
- User có thể thay đổi `Serial.begin(115200)` trong sketch — hệ thống không biết.
- Cần để user chọn baud rate khi gửi Flash request (trong Flash Dialog).
- Baud rate phải được truyền theo suốt pipeline: Dialog → API → worker → broker serial-capture.

#### Feature D — Board-aware device intake / pending review workflow
- Khi cắm ESP32 và ESP8266 vào cùng server, cả hai đều hiện `type = ESP_CH340`.
- Chọn board trong Flash Dialog (ESP32/ESP8266) KHÔNG có tác dụng lọc thiết bị.
- Cần phân loại board thật (`esp32 / esp8266 / arduino_uno`) cho từng device.
- Workflow cần:
  1. Thiết bị lần đầu cắm vào → `usage_mode = block`, `review_state = pending_review`.
  2. Admin thấy "hộp chờ" (pending review box) với số thiết bị chưa phân loại.
  3. Admin nhập tên thiết bị + chọn `board_class` → xác nhận → thiết bị rời hộp chờ.
  4. Thiết bị đã phân loại mới xuất hiện tại Device Management để đổi usage_mode.
  5. Flash Dialog chỉ hiển thị thiết bị đã được phân loại, đang kết nối, đúng board_class với board đang chọn.

---

## 3. NGUYÊN TẮC HARD SCOPE

### ĐƯỢC LÀM
- Làm đúng batch đang được duyệt.
- Fix tối thiểu, đúng điểm.
- Bảo vệ toàn bộ luồng ESP32 đang hoạt động tốt.
- Đọc/trace/hiểu trước, rồi mới patch.
- Tái sử dụng foundation hiện có.

### KHÔNG ĐƯỢC LÀM
- Không refactor module không liên quan.
- Không redesign toàn bộ Admin UI.
- Không thay đổi queue rules nếu batch không yêu cầu.
- Không thay đổi DB schema ngoài phạm vi batch.
- Không nói bug đã fix mà không có bước retest cụ thể.
- Không tick checklist trước khi thật sự hoàn thành.

---

## 4. BÀI HỌC BẮT BUỘC PHẢI NHỚ (từ Batch 1 thất bại trước)

> Lần sửa Batch 1 trước đây đã thất bại vì vi phạm các nguyên tắc sau.
> Lần này BẮT BUỘC phải tuân thủ.

### 4.1 Không đụng vào broker serial runtime chung trước khi có evidence
- ESP32 đang tốt. Mọi thay đổi ở serial-capture path chung đều có thể làm hỏng ESP32.
- Chỉ được patch broker serial khi đã xác định chắc chắn nguyên nhân bằng log thực tế.

### 4.2 Tách 2 lỗi — làm từng bài riêng
- Bug B (manual stop) là lỗi logic backend thuần → sửa ở worker, không đụng broker.
- Bug A (ESP8266 serial) là lỗi runtime capture → điều tra bằng evidence, patch nhỏ.

### 4.3 Điều tra ESP8266 bằng đo đạc, không đoán
Trước khi sửa code, phải trả lời bằng log debug thực tế:
- Worker gọi serial-capture lúc nào sau flash?
- Port tại thời điểm đó là gì?
- Broker có mở cổng thành công không?
- Bytes đầu tiên nhận được là gì?
- Log rác (nếu có) là boot ROM, reset line, hay data split?
- Arduino IDE dùng baud và control-line nào khác với broker?

### 4.4 Không gộp nhiều giả thuyết vào một lần patch
- Mỗi lần patch phải giải quyết đúng 1 nguyên nhân đã được chứng minh.
- Sau mỗi patch nhỏ: retest ESP32 ngay để xác nhận không có regression.

### 4.5 Không dùng board-specific hack khi chưa có bằng chứng
Tránh: sleep thêm tùy board, flush buffer tùy board, kéo control lines tùy board.
Chỉ dùng khi có evidence rõ ràng.

---

## 5. BLOCKER POLICY

Nếu gặp blocker:
1. Dừng ngay, không mở rộng phạm vi.
2. Báo cáo:
   - Blocker cụ thể là gì
   - Ảnh hưởng đến đâu
   - Bước an toàn nhất tiếp theo
3. Chờ duyệt trước khi làm bất kỳ thay đổi kiến trúc nào.

Không bịa fix, không bịa kết quả runtime, không bịa xác nhận.

---

## 6. BATCH 1 — SỬA BUG A + B + FEATURE C

### Thứ tự thực hiện bắt buộc trong Batch 1

```
Bước 1 → Fix Bug B (manual stop) ở worker
Bước 2 → Verify ESP32 stop-live pass (không được bỏ qua)
Bước 3 → Thêm instrumentation logging tạm thời cho ESP8266 capture
Bước 4 → Đọc log, xác định root cause ESP8266 serial
Bước 5 → Patch nhỏ đúng điểm, retest ESP32 ngay sau
Bước 6 → Thêm baud rate selector (Feature C)
```

---

### Bug B — Manual stop đánh sai `failed`

#### Triệu chứng
- Flash xong, serial stream đang chạy đúng.
- User nhấn stop.
- History → `failed`.
- Log: `"Serial capture interrupted before the live session could finish."`

#### Root cause đã xác định
- Worker state machine: owner stop → `interrupted` → finalize path → `failed`.
- Đây là lỗi logic thuần ở backend worker, không liên quan broker.

#### Yêu cầu sau fix
- Manual stop sau flash thành công KHÔNG được đổi status thành `failed`.
- Request phải giữ nguyên `success`.
- Append log: `"Live serial session stopped early by user."`
- Device lock phải được release sạch.
- Serial output đã capture trước khi stop phải được giữ nguyên.

#### Ràng buộc
- Chỉ sửa worker state machine.
- Không đụng broker serial timing.
- Không đụng frontend nếu backend đã đủ.

---

### Bug A — ESP8266 serial output không lưu được

#### Triệu chứng
- Flash thành công.
- Sketch chạy thật (Arduino IDE xác nhận: `ESP8266: LED ON / OFF` đúng baud 115200).
- `serial_log` trống, History không hiển thị serial.

#### Quy trình điều tra bắt buộc trước khi patch
Thêm instrumentation log tạm thời để trả lời:
1. Worker gọi serial-capture endpoint lúc nào sau khi flash xong?
2. Port device thực tế tại thời điểm đó là gì?
3. Broker mở cổng thành công hay lỗi?
4. Baud rate đang dùng là bao nhiêu?
5. Broker nhận được bytes đầu tiên không? Nội dung là gì?
6. Có re-enumeration USB sau flash không? Port có đổi tên không?
7. So sánh: Arduino IDE đang dùng baud/control-line gì khác với broker?

Sau khi có evidence → xác định root cause → mới patch.

#### Yêu cầu sau fix
- ESP8266 serial capture hoạt động như ESP32 path.
- Captured serial được lưu vào `serial_log`.
- History hiển thị đúng serial output.

#### Ràng buộc
- Bảo vệ ESP32 path: sau mỗi patch nhỏ phải retest ESP32.
- Không dùng heuristic board-specific khi chưa có evidence.
- Không gộp nhiều giả thuyết vào một lần patch.

---

### Feature C — Baud rate selector

#### Vấn đề
- Baud rate hiện bị hardcode trong broker.
- User có thể đặt bất kỳ baud nào trong `Serial.begin(...)`.
- Không khớp baud → serial output rác hoặc trống.

#### Yêu cầu
- Trong Flash Dialog: thêm dropdown chọn baud rate.
- Giá trị mặc định: `115200`.
- Các lựa chọn tối thiểu: `9600 / 19200 / 38400 / 57600 / 74880 / 115200 / 230400 / 460800 / 921600`.
- Baud rate được truyền theo pipeline: Flash Dialog → API request → worker → broker serial-capture.
- Broker mở serial port với đúng baud rate đã chọn.
- Baud rate hiển thị trong History detail của request đó.

#### Ràng buộc
- Không thay đổi flash logic, chỉ thêm tham số baud vào pipeline serial-capture.
- Giá trị default `115200` đảm bảo backward compatible.

---

### Format báo cáo sau Batch 1

Chỉ trả về:
1. Exact files đã thay đổi
2. Root cause của Bug A (ESP8266 serial)
3. Root cause của Bug B (manual stop failed)
4. Fix cụ thể cho từng bug
5. Thay đổi pipeline cho Feature C (baud selector)
6. Bước retest thủ công
7. Có cần backup không

---

## 7. BATCH 2 — BOARD-AWARE DEVICE INTAKE & PENDING REVIEW

> **Chỉ bắt đầu Batch 2 sau khi Batch 1 được xác nhận thủ công.**

### Vấn đề gốc rễ

Hiện tại:
- Tất cả device USB-serial đều có `type = ESP_CH340` (hoặc tương tự).
- `type` phản ánh USB bridge chip, KHÔNG phải board thật.
- ESP32 và ESP8266 cùng hiện là `ESP_CH340` → không phân biệt được.
- Chọn board trong Flash Dialog KHÔNG lọc device → vô nghĩa.
- Thiết bị mới cắm vào là có thể dùng ngay → không an toàn.

### Hành vi mới sau Batch 2

#### 7.1 Device mới cắm vào
- Mặc định: `usage_mode = block`, `review_state = pending_review`.
- KHÔNG xuất hiện trong Device Management (bảng chính).
- Xuất hiện trong "Hộp chờ" (Pending Review Box) của Admin.

#### 7.2 Admin Pending Review Box
- Hiển thị số thiết bị chờ phân loại (badge/counter).
- Hiển thị danh sách thiết bị pending: tag_name, type, port, thời gian phát hiện.
- Admin bấm vào từng thiết bị → mở form phân loại:
  - Nhập **Device Name** (tên tự đặt, ví dụ: "ESP8266_TEST").
  - Chọn **Board Class**: `esp32 / esp8266 / arduino_uno`.
  - Nút **[Xác nhận & Phân loại]**.
- Sau khi xác nhận:
  - `review_state` → `approved`.
  - `board_class` được lưu.
  - Thiết bị rời khỏi Pending Review Box.
  - Thiết bị xuất hiện tại Device Management (vẫn ở `usage_mode = block`).
  - Admin tự quyết định đổi sang `free` hay `share` tại Device Management.

#### 7.3 Device Management (bảng chính)
- Chỉ hiển thị thiết bị có `review_state = approved`.
- Thiết bị pending không xuất hiện ở đây.

#### 7.4 Flash Dialog
Chỉ hiển thị device thỏa mãn TẤT CẢ điều kiện sau:
- `review_state = approved`
- Đang kết nối (connected)
- `board_class` khớp với board đang chọn (ESP32/ESP8266/Arduino Uno)
- Vượt qua kiểm tra `usage_mode` / share permission hiện có

#### 7.5 Schema changes
Thêm vào bảng `devices`:
```sql
ALTER TABLE devices
  ADD COLUMN board_class ENUM('esp32', 'esp8266', 'arduino_uno') DEFAULT NULL,
  ADD COLUMN review_state ENUM('pending_review', 'approved') DEFAULT 'pending_review';
```

> **Ưu tiên**: Extend bảng `devices` hiện có, KHÔNG tạo bảng mới trừ khi có lý do kiến trúc rõ ràng.

### Batch 2 constraints
- Bảo vệ Phase 3C queue/flash/serial flow.
- Tái sử dụng Admin UI foundation hiện có (3D-A / 3D-B).
- Không redesign toàn bộ Admin UI.

### Format báo cáo sau Batch 2

Chỉ trả về:
1. Exact files đã thay đổi
2. Schema/API changes cụ thể
3. Pending-review workflow đã thêm
4. Flash Dialog filtering dùng `board_class` như thế nào
5. Bước retest thủ công
6. Có cần backup không

---

## 8. THỨ TỰ THỰC HIỆN BẮT BUỘC

```
[Batch 1]
  Bước 1: Fix Bug B (worker manual stop logic)
  Bước 2: Verify ESP32 stop-live không bị ảnh hưởng
  Bước 3: Instrument logging ESP8266 serial capture
  Bước 4: Đọc log → xác định root cause
  Bước 5: Patch ESP8266 serial (nhỏ, có retest ESP32)
  Bước 6: Thêm Feature C (baud selector)
  Bước 7: Manual retest Batch 1

[Chờ xác nhận thủ công]

[Batch 2]
  Bước 8: Schema: thêm board_class + review_state
  Bước 9: Logic device mới → pending_review + block
  Bước 10: Admin Pending Review Box UI
  Bước 11: Admin classify flow (name + board_class + confirm)
  Bước 12: Device Management chỉ hiện approved
  Bước 13: Flash Dialog filter theo board_class + permissions
  Bước 14: Manual retest Batch 2

[Chờ xác nhận thủ công]
```

**Không bắt đầu Batch 2 trước khi Batch 1 được người dùng xác nhận.**

---

## 9. RETEST EXPECTATIONS

### Retest Batch 1 (tối thiểu)
1. ESP8266 compile → flash → serial log với baud 115200 có dữ liệu trong History.
2. ESP8266 compile → flash → serial log với baud 9600 (test baud selector).
3. ESP32 flash thành công → nhấn stop → request giữ `success`, không `failed`.
4. Partial serial output trước khi stop vẫn hiển thị trong History.
5. Device lock được release sạch sau stop.
6. ESP32 serial vẫn hoạt động bình thường (kiểm tra không có regression).

### Retest Batch 2 (tối thiểu)
1. Cắm thiết bị mới → xuất hiện trong Pending Review Box, KHÔNG xuất hiện trong Device Management.
2. Admin phân loại thiết bị (đặt tên + chọn board_class) → confirm.
3. Thiết bị approved xuất hiện trong Device Management với `usage_mode = block`.
4. Admin đổi sang `free` → user thấy device trong Flash Dialog đúng board_class.
5. Flash Dialog chọn "ESP32" chỉ hiển thị device có `board_class = esp32`.
6. Flash Dialog chọn "ESP8266" chỉ hiển thị device có `board_class = esp8266`.
7. `block/share/free` rules vẫn hoạt động sau classification flow.

---

## 10. OUTPUT DISCIPLINE

- Mỗi response phải ngắn gọn và có cấu trúc rõ ràng.
- Không thêm ý tưởng redesign ngoài phạm vi nếu không được hỏi.
- Không nói "đã xác nhận" nếu chưa thực sự chạy/kiểm tra.
- Nếu cần rebuild Docker/container, nói rõ.
- Nếu cần migration DB, cung cấp script SQL cụ thể.

---

## 11. TASK CHECKLIST
> Cập nhật sau mỗi phiên làm việc.
> `[ ]` Chưa bắt đầu | `[~]` Đang làm | `[x]` Xong | `[!]` Blocked

### Batch 1 — Bug fixes + Baud selector

#### Bug B — Manual stop wrongly marks failed
- [x] Trace worker state machine: tìm nhánh map manual stop → interrupted → failed
- [x] Fix worker: manual stop sau flash thành công giữ nguyên `success`
- [x] Append log: "Live serial session stopped early by user."
- [x] Verify device unlock sạch sau manual stop
- [x] Verify partial serial output được giữ lại
- [x] Retest: ESP32 stop-live → status = success ✓

#### Bug A — ESP8266 serial not captured
- [x] Thêm instrumentation logging tạm thời vào serial-capture path
- [x] Chạy ESP8266 flash, đọc log: port, baud, bytes đầu tiên, timing
- [x] Xác định root cause (re-enumeration? timing? baud mismatch? port stale?)
- [x] Patch đúng điểm, nhỏ và đảo ngược được
- [x] Retest ESP32 ngay sau mỗi patch (không để regression)
- [x] Xác nhận ESP8266 serial_log có dữ liệu trong History

#### Feature C — Baud rate selector
- [x] Thêm baud dropdown vào Flash Dialog (default 115200)
- [x] Truyền baud theo pipeline: API request → worker → broker
- [x] Broker mở serial port với baud đã chọn
- [x] Baud rate hiển thị trong History detail
- [x] Retest: flash với baud 9600 và 115200, kiểm tra log đúng

#### Batch 1 wrap-up
- [x] Manual retest toàn bộ Batch 1 completed
- [x] Xóa instrumentation logging tạm thời (nếu đã thêm)

---

### Batch 2 — Board-aware intake & pending review

#### Schema & backend
- [x] Thêm `board_class` và `review_state` vào bảng `devices`
- [x] Logic: device mới phát hiện → `usage_mode = block`, `review_state = pending_review`
- [ ] API: GET pending devices (admin only)
- [ ] API: POST classify device (name + board_class → approved)

#### Admin UI
- [ ] Pending Review Box: hiển thị số thiết bị chờ (badge)
- [ ] Pending Review Box: danh sách thiết bị pending với thông tin cơ bản
- [ ] Form phân loại: nhập Device Name + chọn board_class + nút xác nhận
- [ ] Sau classify: thiết bị rời Pending Box, xuất hiện trong Device Management

#### Device Management
- [ ] Bảng chính chỉ hiện device `review_state = approved`
- [ ] Thiết bị pending KHÔNG xuất hiện trong bảng chính

#### Flash Dialog
- [ ] Filter: chỉ hiện device approved + connected + board_class khớp board đang chọn
- [ ] Filter: vẫn áp dụng usage_mode / share permission checks hiện có

#### Batch 2 wrap-up
- [ ] Manual retest toàn bộ Batch 2 completed

---

*Last updated: 2026-04-13*
*Tác giả: dựa trên phase3-master-plan.md + Plan_Fix_Bug_Batch.md + Batch1_Serial_Fix_Lessons_Learned.md*
