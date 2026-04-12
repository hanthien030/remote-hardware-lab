# file: compiler/app/main.py
"""
Compiler Service — nhận code C++ và compile thành .bin dùng Arduino CLI.
Hỗ trợ cả sync /compile và SSE streaming /compile-stream.

Entry-point strategy (5 cases):
  Case 1: Only .ino (non-empty)           → use .ino as entry, .cpp as libs
  Case 2: .ino + .cpp (both non-empty)    → use .ino as entry, .cpp as libs
  Case 3: Only .cpp, no .ino             → rename main.cpp → sketch.ino (Arduino.h included)
  Case 4: Empty .ino + .cpp              → treat empty .ino as absent → Case 3
  Case 5: .ino + empty .cpp              → treat empty .cpp as absent → Case 1
"""

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import glob
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Generator, Dict

app = FastAPI(
    title="Remote Lab Compiler",
    description="Arduino CLI compilation service.",
    version="2.0.0",
)

# Board mapping: friendly name → FQBN (Fully Qualified Board Name)
BOARD_MAP = {
    "esp32":         "esp32:esp32:esp32",
    "esp32dev":      "esp32:esp32:esp32",
    "esp32s2":       "esp32:esp32:esp32s2",
    "esp8266":       "esp8266:esp8266:nodemcuv2",
    "arduino_uno":   "arduino:avr:uno",
    "arduino_mega":  "arduino:avr:mega",
    "arduino_nano":  "arduino:avr:nano",
}

DEFAULT_BOARD = "esp32:esp32:esp32"
FLASH_TOOL_HINTS = {
    "esp32": "esptool",
    "esp32dev": "esptool",
    "esp32s2": "esptool",
    "esp8266": "esptool",
    "arduino_uno": "avrdude",
    "arduino_mega": "avrdude",
    "arduino_nano": "avrdude",
}


def _sse_event(data: dict) -> str:
    """Format a single SSE event."""
    return f"data: {json.dumps(data)}\n\n"


def _is_empty(content: str) -> bool:
    """Return True if file has no real code (only whitespace/comments)."""
    stripped = re.sub(r'//[^\n]*', '', content)           # single-line comments
    stripped = re.sub(r'/\*.*?\*/', '', stripped, flags=re.DOTALL)  # block comments
    return len(stripped.strip()) == 0


def _find_firmware_bin(build_dir: str) -> Optional[str]:
    """Find the main firmware .bin (exclude partition/bootloader files)."""
    for f in glob.glob(os.path.join(build_dir, "*.bin")):
        name = os.path.basename(f)
        if "partition" not in name and "bootloader" not in name and "boot_app" not in name:
            return f
    return None


def _find_firmware_hex(build_dir: str) -> Optional[str]:
    """Find the main firmware .hex, preferring the non-bootloader image."""
    preferred = []
    fallback = []
    for artifact_path in glob.glob(os.path.join(build_dir, "*.hex")):
        name = os.path.basename(artifact_path).lower()
        if "with_bootloader" in name or "bootloader" in name:
            fallback.append(artifact_path)
        else:
            preferred.append(artifact_path)

    matches = sorted(preferred) or sorted(fallback)
    return matches[0] if matches else None


def _find_first_artifact(build_dir: str, pattern: str) -> Optional[str]:
    matches = sorted(glob.glob(os.path.join(build_dir, pattern)))
    return matches[0] if matches else None


def _resolve_compile_artifact(board: str, build_dir: str) -> Optional[Dict]:
    normalized_board = board.lower()
    artifact_path = None

    if normalized_board.startswith("esp32") or normalized_board == "esp8266":
        artifact_path = _find_firmware_bin(build_dir)
    elif normalized_board.startswith("arduino_"):
        artifact_path = _find_firmware_hex(build_dir)

    if not artifact_path:
        return None

    artifact_ext = os.path.splitext(artifact_path)[1].lower()
    flash_tool_hint = FLASH_TOOL_HINTS.get(normalized_board)
    flash_layout = None
    if normalized_board.startswith("esp32"):
        flash_layout = _build_esp32_flash_layout(build_dir, artifact_path)

    return {
        "path": artifact_path,
        "filename": os.path.basename(artifact_path),
        "ext": artifact_ext,
        "flash_tool_hint": flash_tool_hint,
        "flash_layout": flash_layout,
    }


def _encode_flash_segments(segment_sources: List[tuple]) -> List[dict]:
    segments = []
    for offset, source_path in segment_sources:
        with open(source_path, "rb") as artifact_file:
            artifact_bytes = artifact_file.read()
        segments.append({
            "offset": offset,
            "filename": os.path.basename(source_path),
            "base64": base64.b64encode(artifact_bytes).decode(),
            "size_bytes": len(artifact_bytes),
        })
    return segments


def _build_esp32_layout_from_flasher_args(build_dir: str) -> Optional[dict]:
    flasher_args_path = os.path.join(build_dir, "flasher_args.json")
    if not os.path.isfile(flasher_args_path):
        return None

    with open(flasher_args_path, "r", encoding="utf-8") as flasher_args_file:
        payload = json.load(flasher_args_file)

    flash_files = payload.get("flash_files") or {}
    if not flash_files:
        return None

    segment_sources = []
    for offset, relative_path in sorted(flash_files.items(), key=lambda item: int(item[0], 16)):
        source_path = os.path.join(build_dir, relative_path.replace("/", os.sep))
        if not os.path.isfile(source_path):
            return None
        segment_sources.append((offset, source_path))

    flash_settings = payload.get("flash_settings") or {}
    return {
        "tool": "esptool.py",
        "flash_mode": flash_settings.get("flash_mode"),
        "flash_freq": flash_settings.get("flash_freq"),
        "flash_size": flash_settings.get("flash_size"),
        "segments": _encode_flash_segments(segment_sources),
    }


def _build_esp32_layout_from_flash_args(build_dir: str) -> Optional[dict]:
    flash_args_path = os.path.join(build_dir, "flash_args")
    if not os.path.isfile(flash_args_path):
        return None

    with open(flash_args_path, "r", encoding="utf-8") as flash_args_file:
        lines = [line.strip() for line in flash_args_file.readlines() if line.strip()]

    if not lines:
        return None

    tokens = lines[0].split()
    flash_settings = {
        "flash_mode": None,
        "flash_freq": None,
        "flash_size": None,
    }
    for index, token in enumerate(tokens[:-1]):
        if token == "--flash_mode":
            flash_settings["flash_mode"] = tokens[index + 1]
        elif token == "--flash_freq":
            flash_settings["flash_freq"] = tokens[index + 1]
        elif token == "--flash_size":
            flash_settings["flash_size"] = tokens[index + 1]

    segment_sources = []
    for line in lines[1:]:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        offset, relative_path = parts
        source_path = os.path.join(build_dir, relative_path.replace("/", os.sep))
        if not os.path.isfile(source_path):
            return None
        segment_sources.append((offset, source_path))

    if not segment_sources:
        return None

    return {
        "tool": "esptool.py",
        **flash_settings,
        "segments": _encode_flash_segments(segment_sources),
    }


def _build_esp32_flash_layout(build_dir: str, firmware_bin: str) -> Optional[dict]:
    generated_layout = _build_esp32_layout_from_flasher_args(build_dir)
    if generated_layout:
        return generated_layout

    generated_layout = _build_esp32_layout_from_flash_args(build_dir)
    if generated_layout:
        return generated_layout

    bootloader_bin = _find_first_artifact(build_dir, "*.bootloader.bin")
    partitions_bin = _find_first_artifact(build_dir, "*.partitions.bin")

    if not bootloader_bin or not partitions_bin:
        return None

    segment_sources = [
        ("0x1000", bootloader_bin),
        ("0x8000", partitions_bin),
        ("0x10000", firmware_bin),
    ]

    return {
        "tool": "esptool.py",
        "segments": _encode_flash_segments(segment_sources),
    }


class CompileRequest(BaseModel):
    code: str
    board: str = "esp32"
    libraries: Optional[List[str]] = []


class CompileStreamRequest(BaseModel):
    files: dict   # {relative_path: content}
    board: str = "esp32"
    libraries: Optional[List[str]] = []


class CompileResponse(BaseModel):
    ok: bool
    artifact_base64: Optional[str] = None
    artifact_filename: Optional[str] = None
    artifact_ext: Optional[str] = None
    flash_tool_hint: Optional[str] = None
    bin_base64: Optional[str] = None
    bin_filename: Optional[str] = None
    size_bytes: Optional[int] = None
    compile_log: str = ""
    error: Optional[str] = None


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok", "message": "Compiler service running"}


@app.get("/boards")
def list_boards():
    return {"boards": list(BOARD_MAP.keys()), "default": "esp32"}


@app.post("/compile", response_model=CompileResponse)
def compile_firmware(req: CompileRequest):
    """[Legacy] Sync compile from single source code."""
    fqbn = BOARD_MAP.get(req.board.lower(), req.board)
    tmpdir = tempfile.mkdtemp(prefix="remotelab_compile_")
    sketch_dir = os.path.join(tmpdir, "sketch")
    os.makedirs(sketch_dir)

    try:
        with open(os.path.join(sketch_dir, "sketch.ino"), "w") as f:
            f.write(req.code)

        if req.libraries:
            for lib in req.libraries:
                subprocess.run(["arduino-cli", "lib", "install", lib],
                               capture_output=True, text=True, timeout=60)

        build_dir = os.path.join(tmpdir, "build")
        os.makedirs(build_dir)

        result = subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn,
             "--output-dir", build_dir, "--warnings", "none", sketch_dir],
            capture_output=True, text=True, timeout=180
        )
        compile_log = result.stdout + "\n" + result.stderr

        if result.returncode != 0:
            return CompileResponse(ok=False, compile_log=compile_log,
                                   error=f"Compilation failed (exit {result.returncode})")

        artifact = _resolve_compile_artifact(req.board, build_dir)
        if not artifact:
            return CompileResponse(
                ok=False,
                compile_log=compile_log,
                error=f"Compiled but could not find the expected firmware artifact for board {req.board}",
            )

        with open(artifact["path"], "rb") as artifact_file:
            artifact_data = artifact_file.read()

        response_payload = {
            "ok": True,
            "artifact_base64": base64.b64encode(artifact_data).decode(),
            "artifact_filename": artifact["filename"],
            "artifact_ext": artifact["ext"],
            "flash_tool_hint": artifact["flash_tool_hint"],
            "size_bytes": len(artifact_data),
            "compile_log": compile_log,
        }
        if artifact["ext"] == ".bin":
            response_payload["bin_base64"] = response_payload["artifact_base64"]
            response_payload["bin_filename"] = artifact["filename"]

        return CompileResponse(**response_payload)

    except subprocess.TimeoutExpired:
        return CompileResponse(ok=False, compile_log="", error="Compilation timed out (> 180s)")
    except Exception as e:
        return CompileResponse(ok=False, compile_log="", error=str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/compile-stream")
def compile_stream(req: CompileStreamRequest):
    """
    Compile from project files — SSE streaming log realtime.

    SSE events:
      {"stage": "info",    "log": "..."}
      {"stage": "compile", "log": "<arduino-cli output line>"}
      {"stage": "done",    "artifact_base64": "...", "size_bytes": N, "artifact_filename": "..."}
      {"stage": "error",   "error": "message"}
    """
    fqbn = BOARD_MAP.get(req.board.lower(), req.board)

    def _stream() -> Generator[str, None, None]:
        tmpdir = tempfile.mkdtemp(prefix="remotelab_stream_")
        try:
            # ── 1. Classify files by extension ──
            all_ino   = {p: c for p, c in req.files.items() if p.endswith('.ino')}
            all_cpp   = {p: c for p, c in req.files.items() if p.endswith(('.cpp', '.c'))}
            hdr_files = {p: c for p, c in req.files.items() if p.endswith(('.h', '.hpp'))}
            other_files = {p: c for p, c in req.files.items()
                           if not p.endswith(('.ino', '.cpp', '.c', '.h', '.hpp'))}

            # ── 2. Filter out empty files (whitespace/comments only) ──
            active_ino = {p: c for p, c in all_ino.items() if not _is_empty(c)}
            active_cpp = {p: c for p, c in all_cpp.items() if not _is_empty(c)}

            skipped = len(all_ino) - len(active_ino) + len(all_cpp) - len(active_cpp)

            yield _sse_event({"stage": "info", "log": f"Board: {fqbn}"})
            yield _sse_event({"stage": "info",
                              "log": f"Source files: {len(active_ino)} .ino, "
                                     f"{len(active_cpp)} .cpp, {len(hdr_files)} headers"
                                     + (f" ({skipped} empty skipped)" if skipped else "")})

            # ── 3. Determine sketch folder name ──
            # Arduino CLI rule: sketch_folder/sketch_folder.ino must exist
            if active_ino:
                primary_ino = sorted(active_ino.keys())[0]
                sketch_name = os.path.splitext(os.path.basename(primary_ino))[0]
            else:
                sketch_name = "sketch"

            sketch_dir = os.path.join(tmpdir, sketch_name)
            os.makedirs(sketch_dir)
            yield _sse_event({"stage": "info", "log": f"Sketch: {sketch_name}/"})

            # ══════════════════════════════════════════════════════════════
            # CASE 1 & 2: At least one non-empty .ino exists
            #   .ino = entry point (provides setup/loop)
            #   .cpp = companion library sources (compiled separately)
            #   NEVER auto-generate another .ino → avoids multiple definition
            # ══════════════════════════════════════════════════════════════
            if active_ino:
                for idx, (rel_path, content) in enumerate(sorted(active_ino.items())):
                    orig_name = os.path.basename(rel_path)
                    if idx == 0 and orig_name != f"{sketch_name}.ino":
                        # Primary .ino must match folder name (Arduino CLI rule)
                        dest_name = f"{sketch_name}.ino"
                        yield _sse_event({"stage": "info",
                                          "log": f"  [ino] {orig_name} → {dest_name}"})
                    else:
                        dest_name = orig_name
                        yield _sse_event({"stage": "info", "log": f"  [ino] {dest_name}"})
                    with open(os.path.join(sketch_dir, dest_name), "w", encoding="utf-8") as f:
                        f.write(content)

                # Companion .cpp files (must NOT contain setup/loop if .ino does)
                for rel_path, content in active_cpp.items():
                    safe_name = os.path.basename(rel_path.lstrip("/").replace("..", ""))
                    with open(os.path.join(sketch_dir, safe_name), "w", encoding="utf-8") as f:
                        f.write(content)
                    yield _sse_event({"stage": "info", "log": f"  [cpp] {safe_name}"})

            # ══════════════════════════════════════════════════════════════
            # CASE 3 & 4: No non-empty .ino — only .cpp files
            #   Rename main.cpp → sketch.ino directly
            #   Arduino CLI treats all .ino content as Arduino sketch:
            #   Arduino.h is auto-included → Serial, delay, pinMode work
            # ══════════════════════════════════════════════════════════════
            elif active_cpp:
                sorted_cpp = sorted(active_cpp.keys())
                # Prefer file with "main" in name for entry point
                entry_path = next(
                    (p for p in sorted_cpp if "main" in os.path.basename(p).lower()),
                    sorted_cpp[0]
                )

                # Write entry .cpp as sketch.ino (NOT as .cpp)
                ino_dest = os.path.join(sketch_dir, f"{sketch_name}.ino")
                with open(ino_dest, "w", encoding="utf-8") as f:
                    f.write(active_cpp[entry_path])
                yield _sse_event({"stage": "info",
                                  "log": f"  [cpp→ino] {os.path.basename(entry_path)} "
                                         f"→ {sketch_name}.ino (Arduino.h auto-included)"})

                # Remaining .cpp become companion sources
                for rel_path, content in active_cpp.items():
                    if rel_path == entry_path:
                        continue
                    safe_name = os.path.basename(rel_path.lstrip("/").replace("..", ""))
                    with open(os.path.join(sketch_dir, safe_name), "w", encoding="utf-8") as f:
                        f.write(content)
                    yield _sse_event({"stage": "info", "log": f"  [cpp] {safe_name}"})

            else:
                yield _sse_event({"stage": "error",
                                  "error": "No source files with real content (.ino or .cpp)"})
                return

            # ── 4. Write headers ──
            for rel_path, content in hdr_files.items():
                safe_name = os.path.basename(rel_path.lstrip("/").replace("..", ""))
                with open(os.path.join(sketch_dir, safe_name), "w", encoding="utf-8") as f:
                    f.write(content)
                yield _sse_event({"stage": "info", "log": f"  [hdr] {safe_name}"})

            # ── 5. Write other files (.json, .txt…) ──
            for rel_path, content in other_files.items():
                safe_name = os.path.basename(rel_path.lstrip("/").replace("..", ""))
                with open(os.path.join(sketch_dir, safe_name), "w", encoding="utf-8") as f:
                    f.write(content)

            # ── 6. Install extra libraries if requested ──
            if req.libraries:
                for lib in req.libraries:
                    yield _sse_event({"stage": "info", "log": f"Installing library: {lib}..."})
                    subprocess.run(["arduino-cli", "lib", "install", lib],
                                   capture_output=True, text=True, timeout=60)

            # ── 7. Run Arduino CLI ──
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)
            yield _sse_event({"stage": "info", "log": "Starting Arduino CLI..."})

            proc = subprocess.Popen(
                ["arduino-cli", "compile",
                 "--fqbn", fqbn,
                 "--output-dir", build_dir,
                 "--warnings", "none",
                 "--verbose",
                 sketch_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    yield _sse_event({"stage": "compile", "log": line})

            proc.wait()

            if proc.returncode != 0:
                yield _sse_event({"stage": "error",
                                  "error": f"Compilation failed (exit {proc.returncode})"})
                return

            # ── 8. Find and return .bin ──
            artifact = _resolve_compile_artifact(req.board, build_dir)
            if not artifact:
                yield _sse_event({
                    "stage": "error",
                    "error": f"Compiled OK but the expected firmware artifact for board {req.board} was not found",
                })
                return

            with open(artifact["path"], "rb") as artifact_file:
                artifact_data = artifact_file.read()

            flash_layout = artifact["flash_layout"]
            if req.board.lower().startswith("esp32"):
                if flash_layout:
                    yield _sse_event({
                        "stage": "info",
                        "log": "Detected ESP32 flash bundle and preserved its flash layout metadata.",
                    })
                else:
                    yield _sse_event({
                        "stage": "info",
                        "log": "ESP32 extra flash artifacts were not fully available; only the app binary could be exported.",
                    })

            yield _sse_event({
                "stage": "info",
                "log": f"Saved firmware artifact: {artifact['filename']} ({len(artifact_data)/1024:.1f} KB)",
            })

            yield _sse_event({"stage": "info",
                              "log": f"Artifact size: {len(artifact_data)/1024:.1f} KB"})
            done_event = {
                "stage": "done",
                "artifact_base64": base64.b64encode(artifact_data).decode(),
                "artifact_filename": artifact["filename"],
                "artifact_ext": artifact["ext"],
                "flash_tool_hint": artifact["flash_tool_hint"],
                "size_bytes": len(artifact_data),
                "flash_layout": flash_layout,
            }
            if artifact["ext"] == ".bin":
                done_event["bin_base64"] = done_event["artifact_base64"]
                done_event["bin_filename"] = artifact["filename"]
            yield _sse_event(done_event)

        except Exception as e:
            yield _sse_event({"stage": "error", "error": str(e)})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
