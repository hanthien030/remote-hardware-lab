# file: backend/app/services/hardware_service.py

import os
import requests
from app.db import get_db_connection
from mysql.connector.errors import IntegrityError

# Lấy URL của Broker từ biến môi trường
BROKER_URL = os.getenv("BROKER_URL", "http://broker:8000")

def handle_device_connect(port, vendor_id, product_id, serial_number):
    """
    Xử lý thông minh khi một thiết bị được kết nối, dựa trên quy tắc ưu tiên 3 lớp:
    1. USB Serial Number (ưu tiên cao nhất)
    2. MAC Address (nếu không có serial)
    3. Port (fallback - không nên dùng vì dễ nhầm)
    """
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    device = None
    mac_address = None

    try:
        # ƯU TIÊN 1: TÌM BẰNG USB SERIAL NUMBER
        if serial_number:
            print(f"[INFO] Searching device by serial_number: {serial_number}")
            cursor.execute("SELECT * FROM devices WHERE serial_number = %s", (serial_number,))
            device = cursor.fetchone()
            
            if device:
                print(f"[INFO] Device found by serial_number (ID: {device['id']})")

        # NẾU KHÔNG CÓ SERIAL HOẶC KHÔNG TÌM THẤY, THỬ ƯU TIÊN 2: MAC ADDRESS
        if not device:
            print(f"[INFO] No serial number match. Attempting to interrogate device at {port}...")
            
            try:
                # Backend ra lệnh cho Broker "thẩm vấn" thiết bị tại port mới
                broker_endpoint = f"{BROKER_URL}/interrogate"
                print(f"[INFO] Calling broker at: {broker_endpoint}")
                
                response = requests.post(
                    broker_endpoint, 
                    json={"port": port}, 
                    timeout=20
                )
                response.raise_for_status()
                
                data = response.json()
                mac_address = data.get("mac_address")
                
                if mac_address:
                    print(f"[INFO] MAC address obtained from device: {mac_address}")
                    
                    # Tìm thiết bị theo MAC
                    cursor.execute("SELECT * FROM devices WHERE mac_address = %s", (mac_address,))
                    device = cursor.fetchone()
                    
                    if device:
                        print(f"[INFO] Device found by MAC address (ID: {device['id']})")
                else:
                    print(f"[WARN] Broker did not return MAC address")
                    
            except requests.exceptions.Timeout:
                print(f"[ERROR] Timeout while interrogating device at {port}")
                return False, "Device interrogation timed out.", 504
                
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Failed to interrogate device at {port}: {e}")
                return False, f"Failed to interrogate device: {str(e)}", 500
                
            except Exception as e:
                print(f"[ERROR] Unexpected error during interrogation: {e}")
                return False, f"Unexpected error during interrogation: {str(e)}", 500

        # XỬ LÝ KẾT QUẢ
        if device:
            # THIẾT BỊ ĐÃ TỒN TẠI -> CẬP NHẬT LẠI PORT VÀ STATUS
            print(f"[INFO] Updating existing device (ID: {device['id']}) with new port {port}")
            
            cursor.execute(
                """UPDATE devices 
                   SET status = 'connected', 
                       port = %s, 
                       last_seen = NOW() 
                   WHERE id = %s""", 
                (port, device['id'])
            )
            db.commit()
            
            print(f"[DB INFO] Device reconnected (ID: {device['id']}, Tag: {device['tag_name']}) at port {port}")
            return True, f"Device {device['tag_name']} reconnected.", 200
            
        else:
            # THIẾT BỊ HOÀN TOÀN MỚI -> TẠO BẢN GHI MỚI
            print(f"[INFO] Creating new device entry for port {port}")
            
            # Lấy thông tin từ device_identities
            cursor.execute(
                "SELECT device_type, is_virtualized FROM device_identities WHERE vendor_id = %s AND product_id = %s",
                (vendor_id, product_id)
            )
            identity = cursor.fetchone()
            
            device_type = identity['device_type'] if identity else "Unknown"
            is_virtualized = identity['is_virtualized'] if identity else False
            
            print(f"[INFO] Device type identified as: {device_type} (virtualized: {is_virtualized})")

            # Tạo tag_name duy nhất
            cursor.execute("SELECT COUNT(*) as count FROM devices WHERE type = %s", (device_type,))
            count = cursor.fetchone()['count']
            tag_name = f"{device_type}_{count + 1}"

            # Insert thiết bị mới
            sql_insert = """
                INSERT INTO devices (
                    port, serial_number, mac_address, type, tag_name, 
                    vendor_id, product_id, is_virtualized, status, usage_mode,
                    board_class, review_state, last_seen
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'connected', 'block', %s, 'pending_review', NOW())
            """
            cursor.execute(sql_insert, (
                port, serial_number, mac_address, device_type, 
                tag_name, vendor_id, product_id, is_virtualized, None
            ))
            db.commit()
            
            print(f"[DB INFO] New device added: Tag='{tag_name}', Serial='{serial_number}', MAC='{mac_address}'")
            return True, f"Device {tag_name} registered successfully", 201

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Unexpected error in handle_device_connect: {e}")
        import traceback
        traceback.print_exc()
        return False, f"An unexpected error occurred: {str(e)}", 500
        
    finally:
        cursor.close()


def handle_device_disconnect(port):
    """Cập nhật trạng thái và xóa thông tin port của thiết bị."""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        sql = "UPDATE devices SET status = 'disconnected', port = NULL WHERE port = %s"
        cursor.execute(sql, (port,))
        
        if cursor.rowcount > 0:
            db.commit()
            print(f"[DB INFO] Disconnected device at port {port}")
            return True, "Device status updated to disconnected.", 200
        else:
            print(f"[DB WARN] No device found to disconnect at port {port}")
            return False, "Device not found to update.", 404
            
    except Exception as e:
        db.rollback()
        print(f"[DB ERROR] Error during device disconnect: {e}")
        return False, str(e), 500
        
    finally:
        cursor.close()


def get_all_devices():
    """Lấy danh sách tất cả thiết bị."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM devices ORDER BY created_at DESC")
    devices = cursor.fetchall()
    cursor.close()
    return devices


def update_device_info(current_tag_name, new_tag_name, new_device_name):
    """Cập nhật thông tin của một thiết bị dựa vào tag_name hiện tại."""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE devices SET tag_name = %s, device_name = %s WHERE tag_name = %s",
            (new_tag_name, new_device_name, current_tag_name)
        )
        db.commit()
        
        if cursor.rowcount == 0:
            return False, f"No device found with tag_name: {current_tag_name}"
        return True, "Device updated successfully."
        
    except Exception as e:
        db.rollback()
        return False, str(e)
        
    finally:
        cursor.close()


def create_assignment(user_id, tag_name, expires_at, admin_username):
    """Tạo hoặc cập nhật phân quyền thiết bị cho user."""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        sql = """
            INSERT INTO assignments (user_id, tag_name, expires_at, created_by, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE expires_at = VALUES(expires_at), is_active = TRUE
        """
        cursor.execute(sql, (user_id, tag_name, expires_at, admin_username))
        db.commit()
        return True, "Assignment created/updated successfully."
        
    except Exception as e:
        db.rollback()
        return False, str(e)
        
    finally:
        cursor.close()


def get_user_assignments(username):
    """Lấy danh sách thiết bị được phân quyền cho user."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    sql = """
        SELECT d.tag_name, d.type, d.device_name, d.port, d.status,
               d.locked_by_user, a.expires_at
        FROM assignments a
        JOIN devices d ON a.tag_name = d.tag_name
        WHERE a.user_id = %s AND a.is_active = TRUE AND a.expires_at > NOW()
    """
    cursor.execute(sql, (username,))
    assignments = cursor.fetchall()
    cursor.close()
    return assignments


def get_device_by_tag(tag_name):
    """Lấy thông tin chi tiết của một thiết bị bằng tag_name."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM devices WHERE tag_name = %s", (tag_name,))
    device = cursor.fetchone()
    cursor.close()
    return device


def get_device_by_port(port):
    """Lấy thông tin chi tiết của một thiết bị bằng port (e.g. /dev/ttyUSB0)."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM devices WHERE port = %s", (port,))
    device = cursor.fetchone()
    cursor.close()
    return device


def lock_device(tag_name, username):
    """Khóa thiết bị cho một user cụ thể."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM devices WHERE tag_name = %s", (tag_name,))
        device = cursor.fetchone()
        
        if not device:
            return False, "Device not found."
        if device['status'] != 'connected':
            return False, "Device is not connected."
        if device['locked_by_user'] and device['locked_by_user'] != username:
            return False, f"Device is already locked by another user: {device['locked_by_user']}."
        
        cursor.execute("UPDATE devices SET locked_by_user = %s WHERE tag_name = %s", (username, tag_name))
        db.commit()
        return True, "Device locked successfully."
        
    finally:
        cursor.close()


def unlock_device(tag_name, username):
    """Mở khóa thiết bị."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM devices WHERE tag_name = %s", (tag_name,))
        device = cursor.fetchone()
        
        if not device:
            return False, "Device not found."
        if device['locked_by_user'] != username:
            return False, "You do not hold the lock on this device."

        cursor.execute("UPDATE devices SET locked_by_user = NULL WHERE tag_name = %s", (tag_name,))
        db.commit()
        return True, "Device unlocked successfully."
        
    finally:
        cursor.close()
