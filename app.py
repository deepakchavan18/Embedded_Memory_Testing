import os
import sys
import time
import threading
import queue
import json
import subprocess
from flask import Flask, render_template, request, jsonify, Response
from memory_testers import SRAMTester, SDTester, FlashTester, EEPROMTester, get_memory_size, format_size

app = Flask(__name__)

# ---------------- STATE ----------------
test_state = {
    "running": False,
    "progress": 0,
    "bytes_tested": 0,
    "total_size": 0,
    "errors": [],
    "elapsed": 0,
    "eta": 0,
    "write_speed": 0,
    "read_speed": 0,
    "pattern": "random"
}

log_queue = queue.Queue()
cancel_event = threading.Event()

# ---------------- HELPERS ----------------
def emit_log(msg, level="info"):
    log_queue.put(json.dumps({"type": "log", "msg": msg, "level": level}))

def emit_state():
    payload = {
        "type": "state",
        "running": test_state["running"],
        "progress": test_state["progress"],
        "bytes_tested": test_state["bytes_tested"],
        "total_size": test_state["total_size"],
        "errors": len(test_state["errors"]),
        "elapsed": test_state["elapsed"],
        "eta": test_state["eta"],
        "write_speed": test_state.get("write_speed", 0),
        "read_speed": test_state.get("read_speed", 0),
        "bytes_tested_fmt": format_size(test_state["bytes_tested"]),
        "total_size_fmt": format_size(test_state["total_size"]),
    }
    log_queue.put(json.dumps(payload))

# ---------------- UNIT CONVERSION ----------------
def convert_to_bytes(value, unit):
    unit = unit.lower()
    multipliers = {
        "b":  1,
        "kb": 1024,
        "mb": 1024 ** 2,
        "gb": 1024 ** 3,
    }
    return int(float(value) * multipliers.get(unit, 1))

# ---------------- MEMORY DETECTION ----------------
def find_sdcard_mount():
    """
    Returns the mount point (str) of a real removable SD card,
    or None if no SD card is detected.

    Strategy:
    Linux  – scan /sys/block for devices whose 'removable' flag is 1
            and that have an actual mount point (via /proc/mounts).
            Excludes loop devices, USB mass-storage marketed as SSD, etc.
            Common SD host controllers expose names like mmcblk*, sdX with
            removable=1.
    Windows – use wmic to list removable drives (MediaType == 'Removable Media').
    macOS  – parse `diskutil list` for external/physical disks and check mount.
    """
    platform = sys.platform

    if platform.startswith("linux"):
        try:
            # Read /proc/mounts once
            with open("/proc/mounts") as f:
                mounts = {parts[0]: parts[1] for line in f
                        if len(parts := line.split()) >= 2}

            for dev in os.listdir("/sys/block"):
                removable_path = f"/sys/block/{dev}/removable"
                try:
                    with open(removable_path) as f:
                        is_removable = f.read().strip() == "1"
                except OSError:
                    continue

                if not is_removable:
                    continue

                # Check for partitions or the raw device in mounts
                dev_paths = [f"/dev/{dev}"]
                part_dir = f"/sys/block/{dev}"
                for entry in os.listdir(part_dir):
                    if entry.startswith(dev):          # e.g. sdb1, mmcblk0p1
                        dev_paths.append(f"/dev/{entry}")

                for dp in dev_paths:
                    if dp in mounts:
                        return mounts[dp]
        except Exception:
            pass
        return None

    elif platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "logicaldisk", "where", "drivetype=2", "get", "deviceid"],
                capture_output=True, text=True, timeout=5
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip() and l.strip() != "DeviceID"]
            if lines:
                return lines[0]   # e.g. "E:"
        except Exception:
            pass
        return None

    elif platform == "darwin":
        try:
            result = subprocess.run(
                ["diskutil", "list", "-plist", "external", "physical"],
                capture_output=True, text=True, timeout=5
            )
            import plistlib
            pl = plistlib.loads(result.stdout.encode())
            disks = pl.get("WholeDisks", [])
            for disk in disks:
                info = subprocess.run(
                    ["diskutil", "info", "-plist", disk],
                    capture_output=True, text=True, timeout=5
                )
                di = plistlib.loads(info.stdout.encode())
                mp = di.get("MountPoint", "")
                if mp:
                    return mp
        except Exception:
            pass
        return None

    return None


def detect_memory(memory):
    if memory == "sram":
        return True   # Always available (simulated in RAM)
    elif memory == "sdcard":
        return find_sdcard_mount() is not None
    elif memory == "flash":
        return True   # Simulated
    elif memory == "eeprom":
        return True   # Simulated
    return False

# ---------------- RUN ----------------
def run_test(size, memory, pattern):
    test_state["running"] = True
    test_state["progress"] = 0
    test_state["bytes_tested"] = 0
    test_state["total_size"] = size
    test_state["errors"] = []
    test_state["elapsed"] = 0
    test_state["eta"] = 0
    test_state["write_speed"] = 0
    test_state["read_speed"] = 0
    test_state["pattern"] = pattern

    def log(msg, level="info"):
        emit_log(msg, level)

    def update():
        emit_state()

    try:
        if memory == "sram":
            tester = SRAMTester(size)
        elif memory == "sdcard":
            mount = find_sdcard_mount()
            if not mount:
                emit_log("❌ No SD card detected. Please insert an SD card and try again.", "error")
                test_state["running"] = False
                emit_state()
                log_queue.put(json.dumps({"type": "done"}))
                return
            tester = SDTester(mount, size)
        elif memory == "flash":
            tester = FlashTester(size)
        elif memory == "eeprom":
            tester = EEPROMTester(size)
        else:
            emit_log("❌ Unknown memory type", "error")
            test_state["running"] = False
            emit_state()
            log_queue.put(json.dumps({"type": "done"}))
            return

        tester.run(test_state, log, update, cancel_event)

        emit_log(f"📊 Bytes Tested: {format_size(test_state['bytes_tested'])}")
        emit_log(f"📊 Coverage: {test_state['progress']}%")
        emit_log(f"📊 Errors Found: {len(test_state['errors'])}")

    except Exception as e:
        emit_log(f"❌ Error: {str(e)}", "error")

    test_state["running"] = False
    emit_state()
    log_queue.put(json.dumps({"type": "done"}))

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/memory_info", methods=["GET"])
def memory_info():
    memory = request.args.get("memory", "sram")
    size = get_memory_size(memory)
    if memory == "sdcard" and size == 0:
        return jsonify({
            "size_bytes": 0,
            "size_fmt": "Not detected",
            "detected": False
        })
    return jsonify({
        "size_bytes": size,
        "size_fmt": format_size(size),
        "detected": True
    })

@app.route("/start", methods=["POST"])
def start():
    if test_state["running"]:
        return jsonify({"status": "busy"}), 400

    data = request.json
    value = float(data["size"])
    unit = data.get("unit", "b")
    memory = data["memory"]
    pattern = data.get("pattern", "random")

    size = convert_to_bytes(value, unit)

    # Validate against detected memory size
    max_size = get_memory_size(memory)
    if size > max_size:
        return jsonify({
            "status": "error",
            "msg": f"Requested size ({format_size(size)}) exceeds memory capacity ({format_size(max_size)})"
        }), 400

    if size <= 0:
        return jsonify({"status": "error", "msg": "Size must be greater than 0"}), 400

    if not detect_memory(memory):
        return jsonify({"status": "error", "msg": f"Memory '{memory}' not found or not mounted"}), 400

    cancel_event.clear()
    t = threading.Thread(target=run_test, args=(size, memory, pattern))
    t.daemon = True
    t.start()

    return jsonify({"status": "started"})

@app.route("/stream")
def stream():
    def generate():
        while True:
            try:
                msg = log_queue.get(timeout=30)
                yield f"data: {msg}\n\n"
                if json.loads(msg).get("type") == "done":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/cancel", methods=["POST"])
def cancel():
    cancel_event.set()
    return jsonify({"status": "cancelled"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
