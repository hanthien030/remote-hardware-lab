# file: hardware_manager/listener.py
import logging
import os
import time

import requests
from dotenv import load_dotenv
from serial.tools import list_ports

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:5000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "your-default-secret-key")
POLLING_INTERVAL = int(os.getenv("LISTENER_POLLING_INTERVAL", 5))


def report_to_backend(port_info, event_type='connect'):
    """Send device events to backend for connect and disconnect."""
    if event_type == 'connect':
        endpoint = f"{BACKEND_URL}/api/internal/hardware/discover"
        vid_hex = f"{port_info.vid:04x}" if port_info.vid else None
        pid_hex = f"{port_info.pid:04x}" if port_info.pid else None
        serial = port_info.serial_number

        payload = {
            "port": port_info.device,
            "vendor_id": vid_hex,
            "product_id": pid_hex,
            "serial_number": serial,
        }
        log_message = f"Detected new device: {port_info.device} (SN: {serial}). Reporting to backend..."
    else:
        endpoint = f"{BACKEND_URL}/api/internal/hardware/disconnect"
        payload = {"port": port_info.device}
        log_message = f"Device removed: {port_info.device}. Reporting disconnect to backend..."

    headers = {"X-Internal-API-Key": INTERNAL_API_KEY}
    timeout = 30 if event_type == 'connect' else 10

    try:
        logging.info(log_message)
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        logging.info("Backend handled '%s' event for %s.", event_type, port_info.device)
    except requests.exceptions.HTTPError as exc:
        logging.error(
            "HTTP error while reporting '%s' for %s: %s %s",
            event_type,
            port_info.device,
            exc.response.status_code,
            exc.response.text,
        )
    except requests.exceptions.RequestException as exc:
        logging.error("Could not reach backend while reporting '%s': %s", event_type, exc)


def reconcile_backend_state(active_ports):
    """Run once at startup to clear stale connected rows after crashes/restarts."""
    endpoint = f"{BACKEND_URL}/api/internal/hardware/reconcile"
    headers = {"X-Internal-API-Key": INTERNAL_API_KEY}
    payload = {"active_ports": sorted(active_ports)}

    try:
        logging.info("Starting one-time hardware reconcile with backend...")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("Startup reconcile completed successfully.")
    except requests.exceptions.HTTPError as exc:
        logging.error(
            "HTTP error during startup reconcile: %s %s",
            exc.response.status_code,
            exc.response.text,
        )
    except requests.exceptions.RequestException as exc:
        logging.error("Could not reach backend during startup reconcile: %s", exc)


def main_loop():
    logging.info("Hardware Manager listener started.")
    startup_ports_info = list_ports.comports()
    known_ports = {port.device for port in startup_ports_info}
    reconcile_backend_state(known_ports)

    while True:
        current_ports_info = list_ports.comports()
        current_ports_devices = {port.device for port in current_ports_info}

        new_ports_devices = current_ports_devices - known_ports
        if new_ports_devices:
            for port_info in current_ports_info:
                if port_info.device in new_ports_devices and port_info.vid and port_info.pid:
                    report_to_backend(port_info, event_type='connect')
            known_ports.update(new_ports_devices)

        removed_ports = known_ports - current_ports_devices
        if removed_ports:
            for port_device in removed_ports:
                class FakePortInfo:
                    device = port_device

                report_to_backend(FakePortInfo(), event_type='disconnect')
            known_ports.difference_update(removed_ports)

        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main_loop()
