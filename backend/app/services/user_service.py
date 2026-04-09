# file: backend/app/services/user_service.py

from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db_connection
from mysql.connector.errors import IntegrityError
from app.services import docker_manager 

def create_user(username, password, email, full_name, role='user'):
    """Tạo một user mới và lưu vào CSDL, mật khẩu sẽ được băm."""
    db = get_db_connection()
    cursor = db.cursor()
    
    hashed_password = generate_password_hash(password)
    
    try:
        cursor.execute(
            """INSERT INTO users (username, password, email, full_name, role, status)
               VALUES (%s, %s, %s, %s, %s, 'active')""",
            (username, hashed_password, email, full_name, role)
        )
        db.commit()
        # Sau khi user được tạo thành công trong DB, tiến hành tạo container
        container_success, container_message = docker_manager.create_user_container(username)
        if not container_success:
            pass
        
        return True, "User created successfully."
    except IntegrityError as e:
        # Lỗi khi username hoặc email đã tồn tại
        db.rollback()
        return False, str(e)
    finally:
        cursor.close()

def get_user_by_username(username):
    """Lấy thông tin user từ CSDL bằng username."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True) 
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    return user

def get_user_by_id(user_id):
    """Lấy thông tin user từ CSDL bằng ID."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, full_name, role, status FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    return user

def get_all_users():
    """Lấy danh sách tất cả users (không lấy password)."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, full_name, role, status, created_at FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    cursor.close()
    return users

def update_user_info(user_id, data):
    """Cập nhật thông tin user."""
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        updates = []
        params = []
        
        if 'email' in data:
            updates.append("email = %s")
            params.append(data['email'])
        
        if 'full_name' in data:
            updates.append("full_name = %s")
            params.append(data['full_name'])
        
        if 'password' in data:
            updates.append("password = %s")
            params.append(generate_password_hash(data['password']))
        
        if 'role' in data:
            updates.append("role = %s")
            params.append(data['role'])
        
        if not updates:
            return False, "No fields to update"
        
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, params)
        db.commit()
        
        return True, "User updated successfully"
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        cursor.close()

def delete_user(user_id):
    """Xoá user khỏi DB rồi dọn container Docker."""
    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Bước 1: Lấy username trước khi xoá
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return False, "User not found"

        username = user[0]

        # Bước 2: Xoá khỏi DB và commit
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()
        # ↑ Từ đây DB đã clean. Mọi lỗi phía dưới KHÔNG rollback DB.

    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        cursor.close()

    # Bước 3: Dọn Docker container — tách hoàn toàn khỏi DB transaction
    # Nếu Docker fail, user vẫn được xoá thành công khỏi DB
    container_success, container_message = docker_manager.delete_user_container(username)
    if not container_success:
        # Log cảnh báo nhưng KHÔNG trả về lỗi — DB đã xoá là đủ
        import logging
        logging.getLogger(__name__).warning(
            f"DB deleted user '{username}' nhưng không xoá được container: {container_message}"
        )

    return True, "User deleted successfully"

def check_password(user_password_hash, password):
    """Kiểm tra mật khẩu người dùng cung cấp có khớp với hash trong CSDL không."""
    return check_password_hash(user_password_hash, password)
