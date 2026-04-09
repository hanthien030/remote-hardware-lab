# file: backend/app/logger.py (Phiên bản sửa lỗi)

import json
from app.db import get_db_connection

def log_action(username, action, success=True, details=None):
    """
    Ghi lại một hành động của người dùng vào bảng 'logs'.
    :param username: Username của người thực hiện hành động.
    :param action: Mô tả hành động (ví dụ: 'User Login', 'Create Device').
    :param success: Hành động có thành công hay không (True/False).
    :param details: Một dictionary chứa thông tin chi tiết thêm (sẽ được lưu dưới dạng JSON).
    """
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor()
        
        # Chuyển đổi dictionary details thành chuỗi JSON
        details_json = json.dumps(details) if details else None
        
        cursor.execute(
            """INSERT INTO logs (username, action, success, details)
               VALUES (%s, %s, %s, %s)""",
            (username, action, success, details_json)
        )
        db.commit()
    except Exception as e:
        # Nếu có lỗi khi ghi log, chỉ in ra console để không làm ảnh hưởng đến luồng chính
        print(f"FATAL: Could not write to log table: {e}")
        if db:
            db.rollback()
    finally:
        if cursor:
            cursor.close()