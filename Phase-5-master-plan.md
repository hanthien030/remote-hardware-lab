# PHASE 5 — MASTER PLAN
# Remote Hardware Lab — Board Intelligence, Device Identity Enrichment, and Admin-Focused Hardware Insight
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

## 2. MỤC TIÊU CỦA PHASE 5

Phase 5 tập trung vào **nâng cấp khả năng hiểu thiết bị thật của hệ thống** ở tầng backend + broker, để:

1. **Phân loại board thật tự động** tốt hơn ngay khi thiết bị mới được kết nối.
2. **Thu thập thêm metadata hữu ích** cho admin quản lý, đối chiếu, và truy vết.
3. **Giới hạn thông tin người dùng thường được thấy**, chỉ giữ lại những gì cần thiết để sử dụng an toàn.
4. **Giảm phụ thuộc vào việc admin phải tự đoán thủ công** ESP32 / ESP8266 / Arduino Uno nếu hệ thống đã có thể probe chắc chắn.
5. Tạo nền móng cho các giai đoạn sau như:
   - phân biệt 2 board cùng model rõ ràng hơn,
   - quản lý thiết bị chuyên nghiệp hơn,
   - tăng độ tin cậy của Flash Dialog và quy trình phê duyệt thiết bị.

---

## 3. TRẠNG THÁI DỰ ÁN TRƯỚC KHI BẮT ĐẦU PHASE 5

### 3.1 Những gì đang ổn định và phải bảo vệ

Những phần sau được coi là baseline đang chạy tốt và **không được làm hỏng**:
- ESP32 compile → flash → serial log → History
- ESP8266 compile → flash → serial log → History
- Baud selector trong Flash Dialog
- FIFO queue + device lock/unlock
- Session/auth stabilization
- Usage mode: `free / share / block`
- Pending review workflow ở mức cơ bản
- Admin approve/classify flow cơ bản
- History / serial / stop-live semantics
- Workspace / editor / compile flow

### 3.2 Giới hạn hiện tại cần nâng cấp

Hiện tại hệ thống mới có thể:
- phát hiện USB-serial device mới,
- gán tag_name,
- lưu VID/PID, serial_number nếu có,
- interrogate ở mức cơ bản,
- cho admin nhập `device_name` và chọn `board_class` thủ công.

Nhưng vẫn còn hạn chế:
- `type` hiện chủ yếu phản ánh **USB bridge** (ví dụ `ESP_CH340`), không phải board thật.
- Admin pending-review UI còn thủ công và chưa đủ thông tin để quyết định nhanh.
- Chưa tận dụng hết dữ liệu probe được từ broker/esptool.
- Chưa có phân tầng rõ ràng giữa:
  - **admin-level metadata**
  - **user-visible metadata**
- Chưa có cơ chế chuẩn để hiển thị fingerprint thiết bị thật cho admin.

---

## 4. MỤC TIÊU CHI TIẾT CỦA PHASE 5

### Feature A — Backend/Broker board intelligence
Nâng cấp broker + backend để khi interrogate thiết bị có thể trả về thêm thông tin như:
- `chip_family` / `board_class` suy đoán được (`esp32`, `esp8266`, `arduino_uno`, hoặc `unknown`)
- `chip_name` / `chip_type`
- `mac_address` nếu có
- `flash_size`
- `crystal_freq`
- `usb_serial_number` nếu có
- `vendor_id` / `product_id`
- trạng thái probe thành công hay không
- mức độ tin cậy của kết quả probe

### Feature B — Admin hardware insight
Admin cần xem được **nhiều thông tin hơn** cho mỗi thiết bị để quản lý chính xác:
- Tag name
- Device name
- Port hiện tại
- USB serial number
- MAC address
- Board class
- Chip type
- Flash size
- Crystal frequency
- VID/PID
- review_state
- usage_mode
- trạng thái kết nối
- thời điểm phát hiện gần nhất

### Feature C — User-visible data minimization
User chỉ nên thấy tối thiểu các thông tin cần thiết để sử dụng:
- device_name
- board_class
- tag_name (nếu vẫn cần cho trace/history)
- connection status
- usage eligibility / queue status

User **không nên thấy** các thông tin quá kỹ thuật hoặc nhạy cảm như:
- MAC address
- USB serial number
- VID/PID
- chip internals chi tiết
- raw hardware fingerprint không cần thiết cho mục đích sử dụng

### Feature D — Better pending-review assistance
Khi device mới vào pending review:
- hệ thống nên tự điền sẵn những gì đã probe được,
- admin chỉ cần xác nhận hoặc chỉnh nhẹ,
- chỉ fallback sang chọn tay khi probe không chắc hoặc không đầy đủ.

---

## 5. HARD SCOPE

### ĐƯỢC LÀM
- Nâng cấp backend + broker interrogation/probe path
- Mở rộng schema hoặc API nếu thực sự cần cho metadata mới
- Nâng cấp admin API/UI để hiển thị metadata mở rộng
- Giới hạn thông tin user-facing đúng chủ đích
- Tận dụng dữ liệu probe từ esptool hoặc cơ chế phù hợp khác

### KHÔNG ĐƯỢC LÀM
- Không refactor toàn bộ queue/flash nếu không liên quan
- Không đụng Virtualized / MPU / multi-slot
- Không redesign toàn bộ frontend ngoài phần admin hardware/user-visible filtering liên quan
- Không làm hỏng baseline Phase 4 đã pass
- Không bịa board_class nếu probe không chắc
- Không tự động cấp quyền usable cho device mới chỉ vì probe thành công

---

## 6. NGUYÊN TẮC THIẾT KẾ CỦA PHASE 5

### 6.1 Probe là trợ lý, không phải quyền lực tối thượng
- Hệ thống **có thể tự suy đoán** `board_class`, nhưng admin vẫn là người xác nhận cuối cùng.
- Device mới dù probe thành công vẫn nên giữ:
  - `usage_mode = block`
  - `review_state = pending_review`
- Không auto-open cho user dùng ngay.

### 6.2 Admin thấy nhiều hơn user
- Admin cần metadata sâu để quản lý.
- User chỉ thấy metadata đủ dùng.
- Không để user thường nhìn thấy các fingerprint phần cứng chi tiết nếu không cần.

### 6.3 Không dùng port như danh tính chính
- Port chỉ là runtime locator, không phải identity ổn định.
- Ưu tiên identity theo thứ tự:
  1. USB serial number
  2. MAC address
  3. chip-family / chip-info probe
  4. port chỉ là fallback tạm thời

### 6.4 Mọi auto-detection phải minh bạch
- Nếu hệ thống tự xác định `board_class`, admin phải nhìn thấy:
  - hệ thống đã detect gì
  - mức độ chắc chắn ra sao
- Nếu detect thất bại, UI phải nói rõ là cần chọn tay.

---

## 7. CẤU TRÚC THỰC HIỆN PHASE 5

### Batch 5A — Probe enrichment ở broker/backend
Mục tiêu:
- Nâng cấp interrogation path để trả metadata phong phú hơn.

Phạm vi:
- broker interrogation endpoint
- backend hardware_service ingestion/update path
- schema/API cần thiết cho metadata mới

Yêu cầu:
1. Broker trả được structured probe result khi có thể.
2. Backend lưu metadata probe vào devices hoặc một cấu trúc phù hợp.
3. Không đổi queue rules.
4. Không đổi user-facing UI ở batch này.

### Batch 5B — Admin metadata UI
Mục tiêu:
- Admin nhìn thấy đầy đủ metadata để phân loại và quản lý dễ hơn.

Phạm vi:
- admin devices API
- admin pending-review UI
- admin device detail / row expansion / compact metadata display

Yêu cầu:
1. Pending device phải hiện metadata probe được.
2. Approved device cũng có cách xem metadata đầy đủ.
3. UI phải gọn, không bắt admin nhìn form dài vô tổ chức.
4. Nếu hệ thống đã detect board_class, admin chỉ cần confirm hoặc sửa.

### Batch 5C — User-visible information minimization
Mục tiêu:
- Giới hạn thông tin user thường được thấy.

Phạm vi:
- user device list / flash dialog / history labels nếu cần

Yêu cầu:
1. User chỉ thấy metadata cơ bản.
2. Admin vẫn thấy metadata đầy đủ.
3. Không làm mất traceability nội bộ.

### Batch 5D — Optional confidence/prompt refinement
Mục tiêu:
- Tăng độ tin cậy của pending-review bằng confidence/hint.

Phạm vi:
- chỉ làm nếu Batch 5A–5C ổn định và người dùng muốn tiếp tục.

---

## 8. BATCH 5A — CHI TIẾT

### Bài toán
Hiện tại broker/backend chưa tận dụng hết khả năng probe board thật.
Thực tế thử tay bằng `esptool flash-id` đã phân biệt được:
- ESP32 vs ESP8266
- MAC address
- flash size
- crystal frequency

Nghĩa là hệ thống có cơ sở kỹ thuật để enrich metadata cho admin.

### Yêu cầu sau Batch 5A
1. Broker interrogation phải có thể trả về thêm fields như:
   - `probe_success`
   - `chip_family`
   - `chip_type`
   - `mac_address`
   - `flash_size`
   - `crystal_freq`
   - `probe_source`
   - `probe_confidence`
2. Backend phải ingest và lưu được các fields phù hợp.
3. Nếu `chip_family` ánh xạ chắc chắn sang `board_class`, backend có thể điền sẵn `board_class_detected` hoặc dữ liệu tương đương.
4. Không tự approve device chỉ vì detect thành công.

### Lưu ý triển khai
- Nếu Arduino Uno không probe được theo cùng cách như ESP-class, phải cho phép `unknown` rõ ràng.
- Không ép mọi board đi chung một đường nếu probe path khác bản chất.

---

## 9. BATCH 5B — CHI TIẾT

### Bài toán
Pending-review UI hiện quá thô và khó dùng khi có nhiều device cùng loại USB bridge.

### Yêu cầu sau Batch 5B
1. Pending Review box hiển thị dạng gọn, dễ so sánh nhiều device.
2. Mỗi pending device phải hiện:
   - tag_name
   - port
   - connection status
   - USB serial number (nếu có)
   - MAC address (nếu có)
   - chip family/type (nếu probe được)
   - detected board class (nếu có)
3. Admin approve form nên:
   - auto-fill board class nếu detect chắc chắn
   - cho sửa tay nếu cần
   - nhập device_name
   - confirm
4. Main Device Management có cách xem metadata mở rộng của thiết bị approved, nhưng không làm bảng chính quá rối.

### Gợi ý UI
- bảng compact + expandable row
- hoặc nút “View details” / “Hardware info” riêng cho admin
- không dồn mọi metadata vào 1 bảng ngang dài khó nhìn

---

## 10. BATCH 5C — CHI TIẾT

### Bài toán
User không cần thấy quá nhiều thông tin phần cứng sâu.

### Yêu cầu sau Batch 5C
1. Flash Dialog chỉ hiện những gì user cần:
   - device_name
   - board_class
   - status
   - queue/load
2. User history/device view không lộ MAC / USB serial / VID/PID trừ khi có lý do thật sự cần.
3. Admin endpoints và user endpoints phải phân tầng rõ.

---

## 11. BLOCKER POLICY

Nếu gặp blocker:
1. Dừng ngay trước khi mở rộng phạm vi.
2. Báo cáo:
   - blocker cụ thể
   - ảnh hưởng
   - bước an toàn nhất tiếp theo
3. Chờ duyệt trước khi thay đổi kiến trúc lớn.

Không bịa kết quả probe, không bịa board classification, không bịa metadata.

---

## 12. EXECUTION ORDER

Bắt buộc theo thứ tự:

```text
Step 1: Batch 5A plan/trace current probe path
Step 2: Batch 5A implement broker/backend enrichment
Step 3: Manual verification Batch 5A
Step 4: Batch 5B implement admin metadata UI
Step 5: Manual verification Batch 5B
Step 6: Batch 5C implement user-visible minimization
Step 7: Manual verification Batch 5C
```

Không bắt đầu Batch 5B trước khi Batch 5A được xác nhận thủ công.
Không bắt đầu Batch 5C trước khi Batch 5B được xác nhận thủ công.

---

## 13. RETEST EXPECTATIONS

### Retest Batch 5A
1. Cắm ESP32 mới → backend/broker probe được chip_family / MAC / flash_size nếu có thể.
2. Cắm ESP8266 mới → probe được chip_family / MAC / flash_size nếu có thể.
3. Device mới vẫn vào `pending_review + block`, không auto-approve.
4. Reconnect device cũ không làm mất metadata đã có.

### Retest Batch 5B
1. Pending Review UI hiện metadata probe được.
2. Admin phân biệt được 2 board ESP32 cùng model bằng metadata ổn định.
3. Approve/classify flow vẫn chạy.
4. Device approved vào bảng chính, metadata admin view đúng.

### Retest Batch 5C
1. User Flash Dialog không còn lộ metadata sâu.
2. Admin vẫn xem được metadata đầy đủ.
3. Queue/flash/history không regression.

---

## 14. OUTPUT DISCIPLINE

- Response phải ngắn gọn, có cấu trúc.
- Không claim “auto-detected correctly” nếu chưa test thật.
- Nếu cần migration DB, phải cung cấp SQL cụ thể.
- Nếu cần rebuild broker/backend, phải nói rõ.

---

## 15. TASK CHECKLIST
> Cập nhật sau mỗi phiên làm việc.
> `[ ]` Chưa bắt đầu | `[~]` Đang làm | `[x]` Xong | `[!]` Blocked

### Batch 5A — Broker/backend probe enrichment
- [x] Trace interrogation path hiện tại end-to-end
- [x] Xác định metadata nào broker đã có thể lấy chắc chắn
- [x] Thiết kế response probe mở rộng (chip_family, MAC, flash_size, ...)
- [x] Lưu metadata probe vào backend/devices
- [x] Device mới vẫn giữ `block + pending_review`
- [x] Manual retest Batch 5A completed

### Batch 5B — Admin metadata UI
- [ ] Pending Review box hiển thị metadata probe được
- [ ] Approved device có cách xem metadata mở rộng
- [ ] Admin approve form auto-fill board class khi có detect chắc chắn
- [ ] Admin vẫn sửa tay được nếu detect không chắc
- [ ] Manual retest Batch 5B completed

### Batch 5C — User-visible information minimization
- [ ] Xác định danh sách field admin-only
- [ ] Xác định danh sách field user-visible
- [ ] Flash Dialog chỉ hiện thông tin cơ bản cho user
- [ ] User endpoints không lộ metadata sâu không cần thiết
- [ ] Manual retest Batch 5C completed

---

*Last updated: 2026-04-13*
