# file: hardware_manager/listener.py
import os
import time
import requests
import logging
from dotenv import load_dotenv
from serial.tools import list_ports

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:5000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "your-default-secret-key")
POLLING_INTERVAL = int(os.getenv("LISTENER_POLLING_INTERVAL", 5))

def report_to_backend(port_info, event_type='connect'):
    """Gửi thông tin thiết bị đến backend (cho cả connect và disconnect)."""
    if event_type == 'connect':
        endpoint = f"{BACKEND_URL}/api/internal/hardware/discover"
        vid_hex = f"{port_info.vid:04x}" if port_info.vid else None
        pid_hex = f"{port_info.pid:04x}" if port_info.pid else None
        # Lấy serial number, nếu không có sẽ là None
        serial = port_info.serial_number

        payload = { 
            "port": port_info.device, 
            "vendor_id": vid_hex, 
            "product_id": pid_hex,
            "serial_number": serial # Gửi kèm serial_number (có thể là None)
        }
        log_message = f"Phát hiện thiết bị mới: {port_info.device} (SN: {serial}). Gửi thông tin..."
    else: # event_type == 'disconnect'
        endpoint = f"{BACKEND_URL}/api/internal/hardware/disconnect"
        payload = { "port": port_info.device }
        log_message = f"Thiết bị đã bị rút ra: {port_info.device}. Báo cáo cho backend..."

    headers = { "X-Internal-API-Key": INTERNAL_API_KEY }

    try:
        logging.info(log_message)
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info(f"Backend đã xử lý thành công sự kiện '{event_type}' cho cổng {port_info.device}.")
    except requests.exceptions.HTTPError as e:
        logging.error(f"Lỗi HTTP ({e.response.status_code}) khi báo cáo sự kiện '{event_type}': {e.response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Không thể kết nối đến backend. Lỗi: {e}")

def main_loop():
    logging.info("Hardware Manager (Listener) bắt đầu hoạt động...")
    known_ports = {p.device for p in list_ports.comports()}
    
    while True:
        current_ports_info = list_ports.comports()
        current_ports_devices = {p.device for p in current_ports_info}
        
        # Xử lý kết nối mới
        new_ports_devices = current_ports_devices - known_ports
        if new_ports_devices:
            for port_info in current_ports_info:
                if port_info.device in new_ports_devices and port_info.vid and port_info.pid:
                    report_to_backend(port_info, event_type='connect')
            known_ports.update(new_ports_devices)
        
        # Xử lý ngắt kết nối
        removed_ports = known_ports - current_ports_devices
        if removed_ports:
            # Tạo một đối tượng 'port_info' giả để truyền đi
            for port_device in removed_ports:
                class FakePortInfo:
                    device = port_device
                report_to_backend(FakePortInfo(), event_type='disconnect')
            known_ports.difference_update(removed_ports)
            
        time.sleep(POLLING_INTERVAL)

if __name__ == "__main__":
    main_loop()