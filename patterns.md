## C — Docker / Compiler

### [C-001] Arduino CLI không inject Arduino.h cho file .cpp

**Nguồn:** Task 3B-3 | **Ngày:** 2026-03-30 | **Mức độ:** 🔴 Cao

**Nguyên nhân gốc rễ:**
Arduino CLI chỉ tự động inject Arduino.h và wrap setup()/loop()
cho file .ino — không làm vậy với .cpp.
File .cpp được compile như C++ thuần → Serial, delay, pinMode undefined.

**Pattern để tránh:**
- Nếu user code trong .cpp → rename thành .ino trước khi pass vào arduino-cli
- Lọc file rỗng (strip() == "") trước khi quyết định entry point
- Không dùng #include "main.cpp" trong sketch.ino giả — không hoạt động