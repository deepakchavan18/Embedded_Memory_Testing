import os
import time
import random

# ---------------- HELPERS ----------------
MEMORY_SIZES = {
    "sram": 256 * 1024,           # 256 KB typical SRAM
    "sdcard": 32 * 1024 * 1024 * 1024,  # 32 GB typical SD Card
    "flash": 4 * 1024 * 1024,     # 4 MB typical Flash
    "eeprom": 256 * 1024,         # 256 KB typical EEPROM
}

def get_sdcard_mount():
    """
    Returns the mount point of a real removable SD card, or None.
    Mirrors the logic in app.py so memory_testers stays self-contained.
    """
    import sys, subprocess
    platform = sys.platform

    if platform.startswith("linux"):
        try:
            with open("/proc/mounts") as f:
                mounts = {parts[0]: parts[1] for line in f
                          if len(parts := line.split()) >= 2}
            for dev in os.listdir("/sys/block"):
                try:
                    with open(f"/sys/block/{dev}/removable") as f:
                        if f.read().strip() != "1":
                            continue
                except OSError:
                    continue
                dev_paths = [f"/dev/{dev}"]
                for entry in os.listdir(f"/sys/block/{dev}"):
                    if entry.startswith(dev):
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
            lines = [l.strip() for l in result.stdout.splitlines()
                     if l.strip() and l.strip() != "DeviceID"]
            return lines[0] if lines else None
        except Exception:
            return None

    elif platform == "darwin":
        try:
            import plistlib
            result = subprocess.run(
                ["diskutil", "list", "-plist", "external", "physical"],
                capture_output=True, text=True, timeout=5
            )
            pl = plistlib.loads(result.stdout.encode())
            for disk in pl.get("WholeDisks", []):
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


def get_memory_size(memory):
    """Return the detected or default size of the selected memory in bytes.
    For SD card, returns 0 if no card is detected (no fake fallback)."""
    if memory == "sdcard":
        mount = get_sdcard_mount()
        if mount is None:
            return 0          # Signals "not detected" to the caller
        try:
            stat = os.statvfs(mount)
            return stat.f_frsize * stat.f_blocks
        except Exception:
            return 0
    return MEMORY_SIZES.get(memory, 1024 * 1024)

def get_data_pattern(pattern, chunk=4096):
    if pattern == "zeros":
        return b'\x00' * chunk
    elif pattern == "ones":
        return b'\xFF' * chunk
    elif pattern == "checker":
        return (b'\xAA\x55' * (chunk // 2))
    else:
        return os.urandom(chunk)

def format_size(num_bytes):
    """Human-readable size string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"

# ---------------- SRAM ----------------
class SRAMTester:
    def __init__(self, size):
        self.size = size

    def run(self, state, log, update, cancel):
        log("▶ SRAM Test Started")
        mem = bytearray(self.size)
        start = time.time()
        chunk = max(1, self.size // 200)

        # Write phase
        log("📝 Write Phase...")
        for i in range(self.size):
            if cancel.is_set():
                log("⛔ Test Cancelled", "warning")
                return
            val = i % 256
            mem[i] = val
            if i % chunk == 0:
                elapsed = time.time() - start
                state["bytes_tested"] = i + 1
                state["progress"] = round(((i + 1) / self.size) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = round((elapsed / (i + 1)) * (self.size - i - 1), 1) if i > 0 else 0
                update()

        # Read & Verify phase
        log("🔍 Read & Verify Phase...")
        errors = 0
        for i in range(self.size):
            if cancel.is_set():
                log("⛔ Test Cancelled", "warning")
                return
            if mem[i] != i % 256:
                state["errors"].append(i)
                errors += 1
            if i % chunk == 0:
                elapsed = time.time() - start
                state["bytes_tested"] = self.size + i + 1
                state["progress"] = round(((self.size + i + 1) / (self.size * 2)) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = 0
                update()

        elapsed = time.time() - start
        state["elapsed"] = round(elapsed, 1)
        state["eta"] = 0
        log(f"⏱ Total Time: {elapsed:.2f}s", "info")
        if errors == 0:
            log("✅ SRAM Test Completed — No Errors", "success")
        else:
            log(f"⚠️ SRAM Test Done — {errors} errors found!", "error")


# ---------------- SD CARD ----------------
class SDTester:
    def __init__(self, mount_point, size):
        self.mount = mount_point
        self.size = size
        self.file = os.path.join(mount_point, "memtest_tmp.bin")

    def run(self, state, log, update, cancel):
        chunk = 4096
        data = get_data_pattern(state.get("pattern", "random"), chunk)

        # WRITE
        log("▶ SD Write Test Started")
        written = 0
        start = time.time()

        with open(self.file, "wb") as f:
            while written < self.size:
                if cancel.is_set():
                    log("⛔ Test Cancelled", "warning")
                    return
                to_write = min(chunk, self.size - written)
                f.write(data[:to_write])
                written += to_write
                elapsed = time.time() - start
                speed = (written / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                state["bytes_tested"] = written
                state["progress"] = round((written / self.size) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = round((self.size - written) / (written / elapsed), 1) if elapsed > 0 and written > 0 else 0
                state["write_speed"] = round(speed, 2)
                update()

        write_time = time.time() - start
        write_speed = (self.size / (1024 * 1024)) / write_time
        log(f"🚀 Write Speed: {write_speed:.2f} MB/s", "success")

        # READ
        log("▶ SD Read Test Started")
        read = 0
        start = time.time()

        with open(self.file, "rb") as f:
            while True:
                if cancel.is_set():
                    log("⛔ Test Cancelled", "warning")
                    break
                buf = f.read(chunk)
                if not buf:
                    break
                read += len(buf)
                elapsed = time.time() - start
                speed = (read / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                state["bytes_tested"] = read
                state["progress"] = round((read / self.size) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = round((self.size - read) / (read / elapsed), 1) if elapsed > 0 and read > 0 else 0
                state["read_speed"] = round(speed, 2)
                update()

        read_time = time.time() - start
        read_speed = (self.size / (1024 * 1024)) / read_time
        log(f"🚀 Read Speed: {read_speed:.2f} MB/s", "success")

        try:
            os.remove(self.file)
        except Exception:
            pass

        log("✅ SD Test Completed", "success")


# ---------------- FLASH (SIMULATED) ----------------
class FlashTester:
    def __init__(self, size):
        self.size = size

    def run(self, state, log, update, cancel):
        log("▶ Flash Test (Simulated)")
        chunk = max(1, self.size // 500)
        start = time.time()

        # Erase phase (simulated)
        log("🔥 Erase Phase...")
        for i in range(self.size // 2):
            if cancel.is_set():
                log("⛔ Test Cancelled", "warning")
                return
            if i % chunk == 0:
                elapsed = time.time() - start
                state["bytes_tested"] = i + 1
                state["progress"] = round(((i + 1) / self.size) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = round((elapsed / (i + 1)) * (self.size - i - 1), 1) if i > 0 else 0
                update()
            time.sleep(0.000001)

        # Write phase (simulated)
        log("📝 Program Phase...")
        for i in range(self.size // 2, self.size):
            if cancel.is_set():
                log("⛔ Test Cancelled", "warning")
                return
            if i % chunk == 0:
                elapsed = time.time() - start
                state["bytes_tested"] = i + 1
                state["progress"] = round(((i + 1) / self.size) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = round((elapsed / (i + 1)) * (self.size - i - 1), 1) if i > 0 else 0
                update()
            time.sleep(0.000001)

        elapsed = time.time() - start
        state["elapsed"] = round(elapsed, 1)
        state["eta"] = 0
        log(f"⏱ Total Time: {elapsed:.2f}s", "info")
        log("✅ Flash Test Done", "success")


# ---------------- EEPROM (SIMULATED) ----------------
class EEPROMTester:
    def __init__(self, size):
        self.size = size

    def run(self, state, log, update, cancel):
        log("▶ EEPROM Test (Simulated)")
        chunk = max(1, self.size // 200)
        start = time.time()

        # Byte-write simulation (EEPROM is slow, byte-by-byte)
        log("📝 Byte-Write Phase...")
        for i in range(self.size):
            if cancel.is_set():
                log("⛔ Test Cancelled", "warning")
                return
            if i % chunk == 0:
                elapsed = time.time() - start
                state["bytes_tested"] = i + 1
                state["progress"] = round(((i + 1) / self.size) * 100, 2)
                state["elapsed"] = round(elapsed, 1)
                state["eta"] = round((elapsed / (i + 1)) * (self.size - i - 1), 1) if i > 0 else 0
                update()
            time.sleep(0.0000005)

        elapsed = time.time() - start
        state["elapsed"] = round(elapsed, 1)
        state["eta"] = 0
        log(f"⏱ Total Time: {elapsed:.2f}s", "info")
        log("✅ EEPROM Test Done", "success")
