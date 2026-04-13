# file: backend/app/services/hardware_service.py

import os

import requests
from app.db import get_db_connection
from app.services.flash_queue_service import ACTIVE_STATUSES
from mysql.connector.errors import IntegrityError

# Lay URL cua Broker tu bien moi truong
BROKER_URL = os.getenv("BROKER_URL", "http://broker:8000")
SUPPORTED_BOARD_CLASSES = {"esp32", "esp8266"}


def _empty_probe_result():
    return {
        "probe_success": False,
        "mac_address": None,
        "chip_type": None,
        "chip_family": None,
        "flash_size": None,
        "crystal_freq": None,
    }


def _normalize_chip_family(chip_family):
    if chip_family is None:
        return None

    normalized = str(chip_family).strip().lower()
    if normalized in ("esp32", "esp8266", "unknown"):
        return normalized
    return None


def _detect_board_class(chip_family):
    return chip_family if chip_family in SUPPORTED_BOARD_CLASSES else None


def _probe_device(port):
    probe_result = _empty_probe_result()
    broker_endpoint = f"{BROKER_URL}/interrogate"
    print(f"[INFO] Calling broker interrogation at: {broker_endpoint}")

    try:
        response = requests.post(
            broker_endpoint,
            json={"port": port},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json() or {}
    except requests.exceptions.Timeout:
        print(f"[WARN] Timeout while interrogating device at {port}")
        return probe_result
    except requests.exceptions.RequestException as exc:
        print(f"[WARN] Failed to interrogate device at {port}: {exc}")
        return probe_result
    except ValueError as exc:
        print(f"[WARN] Broker returned invalid JSON for device at {port}: {exc}")
        return probe_result
    except Exception as exc:
        print(f"[WARN] Unexpected error during interrogation for {port}: {exc}")
        return probe_result

    probe_result["probe_success"] = bool(data.get("probe_success"))
    probe_result["mac_address"] = data.get("mac_address") or None
    if probe_result["mac_address"]:
        probe_result["mac_address"] = probe_result["mac_address"].lower()
    probe_result["chip_type"] = data.get("chip_type") or None
    probe_result["chip_family"] = _normalize_chip_family(data.get("chip_family"))
    probe_result["flash_size"] = data.get("flash_size") or None
    probe_result["crystal_freq"] = data.get("crystal_freq") or None

    print(
        "[INFO] Probe result for %s: success=%s chip_family=%s mac=%s"
        % (
            port,
            probe_result["probe_success"],
            probe_result["chip_family"],
            probe_result["mac_address"],
        )
    )
    return probe_result


def handle_device_connect(port, vendor_id, product_id, serial_number):
    """
    Handle device connect using serial number first, then MAC address.
    Probe metadata enriches the device record but must not block discovery.
    """
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    device = None
    probe_result = _probe_device(port)
    mac_address = probe_result["mac_address"]
    detected_board_class = _detect_board_class(probe_result["chip_family"])

    try:
        if serial_number:
            print(f"[INFO] Searching device by serial_number: {serial_number}")
            cursor.execute("SELECT * FROM devices WHERE serial_number = %s", (serial_number,))
            device = cursor.fetchone()

            if device:
                print(f"[INFO] Device found by serial_number (ID: {device['id']})")

        if not device and mac_address:
            print(f"[INFO] Attempting MAC lookup with {mac_address}")
            cursor.execute("SELECT * FROM devices WHERE mac_address = %s", (mac_address,))
            device = cursor.fetchone()

            if device:
                print(f"[INFO] Device found by MAC address (ID: {device['id']})")

        if device:
            print(f"[INFO] Updating existing device (ID: {device['id']}) with new port {port}")

            if probe_result["probe_success"]:
                if device.get("review_state") == "approved":
                    cursor.execute(
                        """UPDATE devices
                           SET status = 'connected',
                               port = %s,
                               last_seen = NOW(),
                               mac_address = %s,
                               chip_type = %s,
                               chip_family = %s,
                               flash_size = %s,
                               crystal_freq = %s
                           WHERE id = %s""",
                        (
                            port,
                            probe_result["mac_address"],
                            probe_result["chip_type"],
                            probe_result["chip_family"],
                            probe_result["flash_size"],
                            probe_result["crystal_freq"],
                            device["id"],
                        ),
                    )
                else:
                    cursor.execute(
                        """UPDATE devices
                           SET status = 'connected',
                               port = %s,
                               last_seen = NOW(),
                               mac_address = %s,
                               chip_type = %s,
                               chip_family = %s,
                               flash_size = %s,
                               crystal_freq = %s,
                               board_class = %s
                           WHERE id = %s""",
                        (
                            port,
                            probe_result["mac_address"],
                            probe_result["chip_type"],
                            probe_result["chip_family"],
                            probe_result["flash_size"],
                            probe_result["crystal_freq"],
                            detected_board_class,
                            device["id"],
                        ),
                    )
            else:
                cursor.execute(
                    """UPDATE devices
                       SET status = 'connected',
                           port = %s,
                           last_seen = NOW()
                       WHERE id = %s""",
                    (port, device["id"]),
                )

            db.commit()
            print(f"[DB INFO] Device reconnected (ID: {device['id']}, Tag: {device['tag_name']}) at port {port}")
            return True, f"Device {device['tag_name']} reconnected.", 200

        print(f"[INFO] Creating new device entry for port {port}")
        cursor.execute(
            "SELECT device_type, is_virtualized FROM device_identities WHERE vendor_id = %s AND product_id = %s",
            (vendor_id, product_id),
        )
        identity = cursor.fetchone()

        device_type = identity["device_type"] if identity else "Unknown"
        is_virtualized = identity["is_virtualized"] if identity else False

        print(f"[INFO] Device type identified as: {device_type} (virtualized: {is_virtualized})")

        cursor.execute("SELECT COUNT(*) as count FROM devices WHERE type = %s", (device_type,))
        count = cursor.fetchone()["count"]
        tag_name = f"{device_type}_{count + 1}"

        sql_insert = """
            INSERT INTO devices (
                port, serial_number, mac_address, chip_type, chip_family, flash_size, crystal_freq, type, tag_name,
                vendor_id, product_id, is_virtualized, status, usage_mode,
                board_class, review_state, last_seen
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'connected', 'block', %s, 'pending_review', NOW())
        """
        cursor.execute(
            sql_insert,
            (
                port,
                serial_number,
                probe_result["mac_address"],
                probe_result["chip_type"],
                probe_result["chip_family"],
                probe_result["flash_size"],
                probe_result["crystal_freq"],
                device_type,
                tag_name,
                vendor_id,
                product_id,
                is_virtualized,
                detected_board_class,
            ),
        )
        db.commit()

        print(
            f"[DB INFO] New device added: Tag='{tag_name}', Serial='{serial_number}', "
            f"MAC='{probe_result['mac_address']}', ChipFamily='{probe_result['chip_family']}'"
        )
        return True, f"Device {tag_name} registered successfully", 201

    except IntegrityError as e:
        db.rollback()
        print(f"[ERROR] Integrity error in handle_device_connect: {e}")
        return False, f"Database integrity error: {str(e)}", 409
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Unexpected error in handle_device_connect: {e}")
        import traceback
        traceback.print_exc()
        return False, f"An unexpected error occurred: {str(e)}", 500

    finally:
        cursor.close()


def handle_device_disconnect(port):
    """Cap nhat trang thai va xoa thong tin port cua thiet bi."""
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
    """Lay danh sach tat ca thiet bi."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM devices ORDER BY created_at DESC")
    devices = cursor.fetchall()
    cursor.close()
    return devices


def update_device_info(current_tag_name, new_tag_name, new_device_name):
    """Cap nhat thong tin cua mot thiet bi dua vao tag_name hien tai."""
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
    """Tao hoac cap nhat phan quyen thiet bi cho user."""
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
    """Lay danh sach thiet bi duoc phan quyen cho user."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    sql = """
        SELECT d.tag_name, d.device_name, d.board_class, d.status
        FROM assignments a
        JOIN devices d ON a.tag_name = d.tag_name
        WHERE a.user_id = %s AND a.is_active = TRUE AND a.expires_at > NOW()
    """
    cursor.execute(sql, (username,))
    assignments = cursor.fetchall()
    cursor.close()
    return assignments


def get_device_by_tag(tag_name):
    """Lay thong tin chi tiet cua mot thiet bi bang tag_name."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM devices WHERE tag_name = %s", (tag_name,))
    device = cursor.fetchone()
    cursor.close()
    return device


def get_device_by_port(port):
    """Lay thong tin chi tiet cua mot thiet bi bang port (e.g. /dev/ttyUSB0)."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM devices WHERE port = %s", (port,))
    device = cursor.fetchone()
    cursor.close()
    return device


def _count_active_flash_requests(cursor, tag_name):
    placeholders = ", ".join(["%s"] * len(ACTIVE_STATUSES))
    cursor.execute(
        f"""
        SELECT COUNT(*) AS active_count
        FROM flash_queue
        WHERE tag_name = %s AND status IN ({placeholders})
        """,
        (tag_name, *ACTIVE_STATUSES),
    )
    row = cursor.fetchone() or {}
    return int(row.get("active_count") or 0)


def reset_device_to_pending_review(tag_name):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM devices WHERE tag_name = %s", (tag_name,))
        device = cursor.fetchone()

        if not device:
            return False, "Device not found.", 404
        if device.get("review_state") != "approved":
            return False, "Only approved devices can be reset to pending review.", 409
        if _count_active_flash_requests(cursor, tag_name) > 0:
            return False, "Device has an active flash request and cannot be reset right now.", 409
        if device.get("locked_by_user"):
            return False, "Device is currently locked and cannot be reset.", 409
        if device.get("in_use_by"):
            return False, "Device is currently in use and cannot be reset.", 409

        cursor.execute(
            """
            UPDATE devices
            SET review_state = 'pending_review',
                board_class = NULL,
                usage_mode = 'block'
            WHERE tag_name = %s AND review_state = 'approved'
            """,
            (tag_name,),
        )
        if cursor.rowcount != 1:
            db.rollback()
            return False, "Device reset failed.", 409

        db.commit()
        return True, "Device moved back to pending review.", 200
    except Exception as e:
        db.rollback()
        return False, str(e), 500
    finally:
        cursor.close()


def delete_device_record(tag_name):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM devices WHERE tag_name = %s", (tag_name,))
        device = cursor.fetchone()

        if not device:
            return False, "Device not found.", 404
        if _count_active_flash_requests(cursor, tag_name) > 0:
            return False, "Device has an active flash request and cannot be deleted.", 409
        if device.get("locked_by_user"):
            return False, "Device is currently locked and cannot be deleted.", 409
        if device.get("in_use_by"):
            return False, "Device is currently in use and cannot be deleted.", 409
        if device.get("status") != "disconnected":
            return False, "Device must be disconnected before deletion.", 409

        cursor.execute("DELETE FROM devices WHERE tag_name = %s", (tag_name,))
        if cursor.rowcount != 1:
            db.rollback()
            return False, "Device deletion failed.", 409

        db.commit()
        return True, "Device record deleted successfully.", 200
    except Exception as e:
        db.rollback()
        return False, str(e), 500
    finally:
        cursor.close()


def lock_device(tag_name, username):
    """Khoa thiet bi cho mot user cu the."""
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
    """Mo khoa thiet bi."""
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
