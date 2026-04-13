import base64
import json
import os
import re
import struct
import subprocess
import tempfile
import time
import shutil
from typing import List, Optional

import serial
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .protocol import CMD_ERASE, CMD_WRITE, FirmwareProtocol

app = FastAPI(
    title='Hardware Access Broker API',
    description='Service trung gian de quan ly va giao tiep voi phan cung.',
    version='0.6.0',
)


class FlashRequest(BaseModel):
    port: str
    firmware_base64: Optional[str] = None
    is_virtualized: bool
    slot_id: Optional[int] = None
    debug: bool = False
    flash_layout: Optional['FlashLayout'] = None


class InterrogateRequest(BaseModel):
    port: str


class PingRequest(BaseModel):
    port: str
    debug: bool = False


class SerialCaptureRequest(BaseModel):
    port: str
    duration_seconds: int
    baud_rate: Optional[int] = 115200


class FlashSegment(BaseModel):
    offset: str
    filename: Optional[str] = None
    base64: str


class FlashLayout(BaseModel):
    tool: Optional[str] = 'esptool.py'
    flash_mode: Optional[str] = None
    flash_freq: Optional[str] = None
    flash_size: Optional[str] = None
    segments: List[FlashSegment]


FlashRequest.model_rebuild()


def flash_virtualized_device(request: FlashRequest):
    if request.slot_id is None:
        raise HTTPException(status_code=400, detail='slot_id is required for virtualized devices')

    protocol = FirmwareProtocol(port=request.port, debug=request.debug)
    try:
        if not protocol.connect():
            raise HTTPException(status_code=500, detail='Could not connect to serial port')

        if not protocol.ping():
            raise HTTPException(
                status_code=500,
                detail='Device not responding to PING. Check if device is in bootloader mode.',
            )

        erase_data = struct.pack('>B', request.slot_id)
        if not protocol.send_command(CMD_ERASE, erase_data):
            raise HTTPException(status_code=500, detail='ERASE command failed')

        firmware_bytes = base64.b64decode(request.firmware_base64)
        chunk_size = 4096
        offset = 0
        total_chunks = (len(firmware_bytes) + chunk_size - 1) // chunk_size

        for index in range(0, len(firmware_bytes), chunk_size):
            chunk = firmware_bytes[index:index + chunk_size]
            write_payload = struct.pack('>B', request.slot_id) + struct.pack('>I', offset) + chunk
            if not protocol.send_command(CMD_WRITE, write_payload):
                raise HTTPException(status_code=500, detail=f'WRITE command failed at offset {offset}')
            offset += len(chunk)

        return {
            'status': 'ok',
            'message': f'Successfully flashed {len(firmware_bytes)} bytes to slot {request.slot_id}',
            'bytes_written': len(firmware_bytes),
            'chunks_written': total_chunks,
        }
    finally:
        protocol.close()


def flash_non_virtualized_device(request: FlashRequest):
    if request.flash_layout and request.flash_layout.segments:
        return flash_non_virtualized_layout(request)

    if not request.firmware_base64:
        raise HTTPException(status_code=400, detail='firmware_base64 is required')

    firmware_bytes = base64.b64decode(request.firmware_base64)

    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as tmp_file:
        tmp_file.write(firmware_bytes)
        tmp_file_path = tmp_file.name

    try:
        command = [
            'esptool.py',
            '--port', request.port,
            'write_flash',
            '0x00000', tmp_file_path,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )

        return {
            'status': 'ok',
            'message': 'Flashed successfully using esptool.py.',
            'bytes_written': len(firmware_bytes),
            'stdout': result.stdout,
        }
    except subprocess.CalledProcessError as exc:
        stderr_out = exc.stderr or ''
        stdout_out = exc.stdout or ''
        raise HTTPException(
            status_code=500,
            detail=f"esptool failed: {stderr_out or stdout_out or 'unknown error'}",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='esptool command timed out.')
    finally:
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)


def flash_non_virtualized_layout(request: FlashRequest):
    if not request.flash_layout or not request.flash_layout.segments:
        raise HTTPException(status_code=400, detail='flash_layout.segments is required')

    tmp_dir = tempfile.mkdtemp(prefix='remotelab_flash_layout_')
    total_bytes = 0

    try:
        command = ['esptool.py', '--port', request.port, 'write_flash']

        if request.flash_layout.flash_mode:
            command.extend(['--flash_mode', request.flash_layout.flash_mode])
        if request.flash_layout.flash_freq:
            command.extend(['--flash_freq', request.flash_layout.flash_freq])
        if request.flash_layout.flash_size:
            command.extend(['--flash_size', request.flash_layout.flash_size])

        for index, segment in enumerate(request.flash_layout.segments):
            filename = segment.filename or f'segment_{index}.bin'
            safe_filename = os.path.basename(filename)
            segment_path = os.path.join(tmp_dir, safe_filename)
            segment_bytes = base64.b64decode(segment.base64)
            with open(segment_path, 'wb') as segment_file:
                segment_file.write(segment_bytes)

            total_bytes += len(segment_bytes)
            command.extend([segment.offset, segment_path])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=180,
        )

        return {
            'status': 'ok',
            'message': 'Flashed successfully using esptool.py flash layout.',
            'bytes_written': total_bytes,
            'stdout': result.stdout,
        }
    except subprocess.CalledProcessError as exc:
        stderr_out = exc.stderr or ''
        stdout_out = exc.stdout or ''
        raise HTTPException(
            status_code=500,
            detail=f"esptool failed: {stderr_out or stdout_out or 'unknown error'}",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='esptool command timed out.')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _serial_capture_stream(request: SerialCaptureRequest):
    connection = None
    bytes_captured = 0

    try:
        duration_seconds = max(1, min(int(request.duration_seconds), 300))
        baud_rate = int(request.baud_rate or 115200)

        connection = serial.Serial()
        connection.port = request.port
        connection.baudrate = baud_rate
        connection.timeout = 0.5
        connection.exclusive = True
        connection.dsrdtr = False
        connection.rtscts = False
        connection.open()
        connection.dtr = False
        connection.rts = False
        connection.reset_input_buffer()
        connection.reset_output_buffer()

        yield json.dumps({
            'type': 'started',
            'port': request.port,
            'duration_seconds': duration_seconds,
            'baud_rate': baud_rate,
        }) + '\n'

        deadline = time.time() + duration_seconds
        while time.time() < deadline:
            pending = connection.in_waiting
            chunk = connection.read(pending or 1)
            if not chunk:
                continue

            decoded = chunk.decode('utf-8', errors='ignore')
            if not decoded:
                continue

            bytes_captured += len(chunk)
            yield json.dumps({
                'type': 'chunk',
                'chunk': decoded,
            }) + '\n'

        yield json.dumps({
            'type': 'finished',
            'reason': 'completed',
            'bytes_captured': bytes_captured,
        }) + '\n'
    except serial.SerialException as exc:
        yield json.dumps({
            'type': 'finished',
            'reason': 'serial_error',
            'error': str(exc),
            'bytes_captured': bytes_captured,
        }) + '\n'
    except Exception as exc:
        yield json.dumps({
            'type': 'finished',
            'reason': 'error',
            'error': str(exc),
            'bytes_captured': bytes_captured,
        }) + '\n'
    finally:
        if connection and connection.is_open:
            connection.close()


@app.get('/healthcheck', tags=['Status'])
def health_check():
    return {'status': 'ok', 'message': 'Broker is running!'}


def _empty_probe_response():
    return {
        'probe_success': False,
        'chip_type': None,
        'chip_family': None,
        'mac_address': None,
        'flash_size': None,
        'crystal_freq': None,
    }


def _extract_probe_field(pattern: str, output: str):
    match = re.search(pattern, output, re.IGNORECASE)
    if not match:
        return None
    value = (match.group(1) or '').strip()
    return value or None


def _map_chip_family(chip_type: Optional[str]):
    if not chip_type:
        return None

    normalized = chip_type.upper()
    if 'ESP32' in normalized:
        return 'esp32'
    if 'ESP8266' in normalized:
        return 'esp8266'
    return 'unknown'


@app.post('/interrogate', tags=['Device Actions'])
def interrogate_device(request: InterrogateRequest):
    command = ['esptool', '--port', request.port, 'flash-id']
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        output = '\n'.join(part for part in [result.stdout, result.stderr] if part)
        chip_type = _extract_probe_field(r'Chip type:\s*(.+)', output)
        mac_address = _extract_probe_field(
            r'MAC:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})',
            output,
        )
        flash_size = _extract_probe_field(r'Detected flash size:\s*(.+)', output)
        crystal_freq = _extract_probe_field(r'Crystal frequency:\s*(.+)', output)

        return {
            'probe_success': True,
            'chip_type': chip_type,
            'chip_family': _map_chip_family(chip_type),
            'mac_address': mac_address.lower() if mac_address else None,
            'flash_size': flash_size,
            'crystal_freq': crystal_freq,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return _empty_probe_response()


@app.post('/ping', tags=['Debug'])
def ping_device(request: PingRequest):
    protocol = FirmwareProtocol(port=request.port, debug=request.debug)
    try:
        if not protocol.connect():
            raise HTTPException(status_code=500, detail='Could not connect to serial port')
        if not protocol.ping():
            raise HTTPException(status_code=500, detail='PING command failed')
        return {'status': 'ok', 'message': 'Device responded to PING'}
    finally:
        protocol.close()


@app.post('/flash-firmware', tags=['Firmware'])
def flash_firmware(request: FlashRequest):
    try:
        if request.is_virtualized:
            return flash_virtualized_device(request)
        return flash_non_virtualized_device(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/serial-capture', tags=['Device Actions'])
def serial_capture(request: SerialCaptureRequest):
    if not request.port:
        raise HTTPException(status_code=400, detail='port is required')
    if request.duration_seconds <= 0:
        raise HTTPException(status_code=400, detail='duration_seconds must be positive')

    return StreamingResponse(
        _serial_capture_stream(request),
        media_type='application/x-ndjson',
    )
