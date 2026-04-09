# file: broker/app/protocol.py

import serial
import struct
import time

# ==============================
# Hằng số giao thức
# ==============================
START_BYTE_CMD = 0xAA
START_BYTE_RES = 0xBB

CMD_PING = 0x01
CMD_ERASE = 0x02
CMD_WRITE = 0x03
CMD_VALIDATE = 0x04
CMD_JUMP = 0x05

STATUS_ACK = 0x00
STATUS_NACK = 0x01

# Map tên lệnh để debug
CMD_NAMES = {
    CMD_PING: "PING",
    CMD_ERASE: "ERASE",
    CMD_WRITE: "WRITE",
    CMD_VALIDATE: "VALIDATE",
    CMD_JUMP: "JUMP",
}


class FirmwareProtocol:
    def __init__(self, port, baud_rate=921600, timeout=5, debug=False):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.debug = debug
        self.serial = None

    def connect(self):
        try:
            # Tạo đối tượng Serial
            self.serial = serial.Serial()
            self.serial.port = self.port
            self.serial.baudrate = self.baud_rate
            self.serial.timeout = self.timeout

            # Mở port với exclusive access (Linux)
            self.serial.exclusive = True
            self.serial.open()

            # Disable DTR/RTS ngay sau khi mở
            self.serial.dtr = False
            self.serial.rts = False

            if self.debug:
                print(f"✓ Connected to {self.port}")
                print("⏳ Waiting for ESP32 to stabilize...")

            # Đợi ESP32 boot xong nếu bị reset
            time.sleep(3)

            # Xóa tất cả boot messages trong RX buffer
            available = self.serial.in_waiting
            if available > 0:
                junk_data = self.serial.read(available)
                if self.debug:
                    print(f"  Cleared {len(junk_data)} bytes of boot messages")
                    if len(junk_data) <= 200:
                        try:
                            print(f"  Boot data: {junk_data.decode('utf-8', errors='ignore')}")
                        except Exception:
                            print(f"  Boot data (hex): {junk_data.hex()}")

            if self.debug:
                print("✓ Ready to communicate")
            return True

        except serial.SerialException as e:
            if self.debug:
                print(f"✗ Error connecting to {self.port}: {e}")
            return False

    def ping(self):
        """Send PING command to test communication"""
        if self.debug:
            print("\n🔔 Testing communication with PING command...")
        return self.send_command(CMD_PING, b'', max_retries=3)

    def _calculate_checksum(self, packet_data):
        checksum = 0
        for byte in packet_data:
            checksum ^= byte
        return checksum

    def send_command(self, cmd, data=b'', max_retries=1):
        if not self.serial:
            if self.debug:
                print("✗ Serial port not connected")
            return False

        cmd_name = CMD_NAMES.get(cmd, f"UNKNOWN(0x{cmd:02X})")
        data_len = len(data)
        len_bytes = struct.pack('>H', data_len)

        # Packet để tính checksum (cmd + length + data)
        packet_to_checksum = bytes([cmd]) + len_bytes + data
        checksum = self._calculate_checksum(packet_to_checksum)

        # Full packet (start + payload + checksum)
        packet = bytes([START_BYTE_CMD]) + packet_to_checksum + bytes([checksum])

        success = False
        for attempt in range(1, max_retries + 1):
            if self.debug:
                print(f"\n{'=' * 60}")
                print(f"→ Sending {cmd_name} command (Attempt {attempt}/{max_retries})")
                print(f"  CMD: 0x{cmd:02X}")
                print(f"  Data Length: {data_len} bytes")
                if 0 < data_len <= 16:
                    print(f"  Data: {data.hex()}")
                elif data_len > 16:
                    print(f"  Data (first 16 bytes): {data[:16].hex()}...")
                print(f"  Full Packet ({len(packet)} bytes): {packet.hex()}")
                print(f"{'=' * 60}")

            # Xóa buffer nhận cũ trước khi gửi lệnh mới
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

            # Gửi packet
            self.serial.write(packet)
            self.serial.flush()

            # Chờ một chút để đảm bảo thiết bị nhận được lệnh
            time.sleep(0.01)

            # Chờ response
            if self.await_response(cmd):
                success = True
                break
            else:
                if self.debug and attempt < max_retries:
                    print(f"✗ Failed on attempt {attempt}. Retrying...")

        return success

    def await_response(self, cmd=None):
        if not self.serial:
            if self.debug:
                print("✗ Serial port not connected")
            return False

        cmd_name = CMD_NAMES.get(cmd, f"UNKNOWN(0x{cmd:02X})") if cmd else "UNKNOWN"

        # Tăng timeout cho ERASE (có thể mất nhiều thời gian)
        wait_timeout = 15 if cmd == CMD_ERASE else self.timeout

        if self.debug:
            print(f"\n← Waiting for {cmd_name} response (timeout={wait_timeout}s)...")

        start_time = time.time()
        response_bytes = []

        # Đọc từng byte cho đến khi đủ 3 bytes hoặc timeout
        while time.time() - start_time < wait_timeout:
            if self.serial.in_waiting > 0:
                byte = self.serial.read(1)
                if byte:
                    byte_val = byte[0]
                    response_bytes.append(byte_val)

                    if self.debug:
                        print(f"  RX byte {len(response_bytes)}: 0x{byte_val:02X}")

                    # Nếu đã thấy START_BYTE_RES và có đủ 3 bytes
                    if START_BYTE_RES in response_bytes:
                        start_idx = response_bytes.index(START_BYTE_RES)
                        if len(response_bytes) >= start_idx + 3:
                            packet = response_bytes[start_idx:start_idx + 3]
                            start_byte, status, checksum = packet

                            if self.debug:
                                print(f"  Status: 0x{status:02X} "
                                      f"({'ACK' if status == STATUS_ACK else 'NACK' if status == STATUS_NACK else 'UNKNOWN'})")
                                print(f"  Checksum: 0x{checksum:02X}")

                            # Xác thực checksum
                            expected_checksum = start_byte ^ status
                            if self.debug:
                                print(f"  Expected Checksum: 0x{expected_checksum:02X}")

                            if expected_checksum == checksum:
                                if self.debug:
                                    print("  ✓ Checksum valid")
                                if status == STATUS_ACK:
                                    if self.debug:
                                        print(f"✓ {cmd_name} command succeeded (ACK received)")
                                    return True
                                else:
                                    if self.debug:
                                        print(f"✗ {cmd_name} command failed (NACK received, status=0x{status:02X})")
                                    return False
                            else:
                                if self.debug:
                                    print(f"✗ Invalid checksum. Expected=0x{expected_checksum:02X}, Got=0x{checksum:02X}")
                                    print(f"  All bytes received: {bytes(response_bytes).hex()}")
                                return False
            else:
                time.sleep(0.01)

        # Timeout
        elapsed = time.time() - start_time
        if self.debug:
            print(f"\n✗ Timeout after {elapsed:.2f}s")
            print(f"  Total bytes received: {len(response_bytes)}")
            if response_bytes:
                print(f"  Received data: {bytes(response_bytes).hex()}")
            else:
                print("  No data received from device")
            print("  Device may not be responding or not in bootloader mode")

        return False

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            if self.debug:
                print("✓ Serial port closed")
