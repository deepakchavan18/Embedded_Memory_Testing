# Memory Tester — Embedded Systems Diagnostic Tool

> A real-time, web-based memory testing dashboard for embedded systems.  
> Supports SRAM, SD Card, Flash, and EEPROM — with live progress, speed metrics, error detection, and full coverage reporting.

▶ YouTube Link - **[Watch Demo on YouTube](https://www.youtube.com/watch?v=wAdavewffqo)**

---

## Overview

**Memory Tester** is a Flask-based diagnostic tool that lets you test embedded memory modules directly from your browser. It provides a live dashboard with byte-level progress, read/write speed, error counts, time elapsed, and ETA — all streamed in real-time using Server-Sent Events (SSE).

Whether you're working with physical hardware (SRAM, Flash, EEPROM, SD Card) or running simulated tests for development, this tool gives you full visibility into your memory's health and performance.

---

## 🗂 Project Structure

```
memory-tester/
├── app.py                  # Flask backend — routes, state management, SSE stream
├── memory_testers.py       # Memory test logic — SRAM, SD Card, Flash, EEPROM
├── templates/
│   └── index.html          # Frontend dashboard UI
└── README.md
```

---

##  Data Flow

![Data Flow](https://i.ibb.co/1G6rcv8m/Screenshot-from-2026-04-22-10-18-24.png)


The system starts with the User Interface, where the user provides test configuration such as memory type, size, and data pattern. These inputs are sent to the Flask Backend, which acts as the control logic and manages the execution of the test.

The backend then performs memory operations, including writing data to memory and reading it back. During this process, an error detection mechanism verifies the correctness of the data to identify any faults.

These operations are executed on either real hardware (e.g., SD card on Raspberry Pi) or simulated memory (SRAM, Flash, EEPROM). The results are continuously processed and sent back to the user interface for real-time monitoring.


The **User Interface** sends a test configuration to the **Flask backend**, which dispatches the appropriate memory tester in a background thread. The tester runs read/write/verify operations against the **hardware or simulation layer**, while continuously pushing state updates back to the UI via a **Server-Sent Events stream**.

---

##  Features

-  **Multi-Memory Support** — SRAM, SD Card (real hardware), Flash (simulated), EEPROM (simulated)
-  **Unit Selector** — Input test size in Bytes, KB, MB, or GB
-  **Auto-detected Memory Capacity** — Shows real device size; prevents over-limit inputs
-  **Data Patterns** — Random, All Zeros (0x00), All Ones (0xFF), Checkerboard (0xAA/0x55)
-  **Live Progress Bar** — Real-time % progress with animated fill
-  **Coverage Display** — Shows how much of total memory was tested (e.g., tested 10% of 32 GB)
-  **Read/Write Speed** — MB/s reported live for SD Card tests
-  **Elapsed Time & ETA** — Always know how long the test will take
-  **Error Detection** — Byte-level mismatch tracking with error count
-  **Live Log Feed** — Timestamped log stream with color-coded severity levels
-  **Cancel Button** — Safely abort any in-progress test
-  **Dark Industrial UI** — Purpose-built embedded systems aesthetic

---

##  Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Realtime Streaming | Server-Sent Events (SSE) |
| Threading | Python `threading`, `queue` |
| Frontend | HTML5, CSS3, JavaScript |
| Tools | VS Code, Raspberry Pi / Linux, Virtual Environment

---

##  Getting Started

### Prerequisites

- Python 3.8+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/memory-tester.git
cd memory-tester

#Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install dependencies
pip install flask
```

### Run

```bash
python app.py
```

Then open your browser at:

```
http://localhost:5000
```

---

##  Usage

1. **Select Memory Type** — Choose from SRAM, SD Card, Flash, or EEPROM.  
   The tool will auto-detect and display the memory capacity.

2. **Enter Test Size** — Type a number and pick a unit (Bytes / KB / MB / GB).  
   If your input exceeds available capacity, the Start button is disabled with a clear warning.

3. **Select Data Pattern** — Choose the write pattern for the test:
   - `Random` — Most realistic worst-case test
   - `All Zeros / All Ones` — Static pattern for quick cell checks
   - `Checkerboard (0xAA/0x55)` — Alternating bits to detect stuck bits

4. **Click Start Test** — The test begins and all stats update live.

5. **Monitor Progress** — Watch the progress bar, coverage %, bytes tested, speed, elapsed time, and ETA.

6. **Cancel Anytime** — Hit the Cancel button to safely stop the test mid-run.

---

##  Memory Test Details

### SRAM
Performs a two-phase test:
- **Write Phase** — Writes `i % 256` to each address
- **Read & Verify Phase** — Reads back and compares; mismatches logged as errors

### SD Card *(requires `/mnt/sdcard` mounted)*
- **Write Test** — Streams selected data pattern to a temp file, reports write speed (MB/s)
- **Read Test** — Reads back the file sequentially, reports read speed (MB/s)
- Temp file is deleted after the test

### Flash *(Simulated)*
- Simulates an **Erase phase** followed by a **Program phase**
- Demonstrates realistic two-stage flash write cycle

### EEPROM *(Simulated)*
- Simulates slow **byte-by-byte write** characteristic of real EEPROM hardware
- Useful for timing and progress visualization

---

##  API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the dashboard UI |
| `/memory_info?memory=<type>` | GET | Returns detected capacity for the selected memory type |
| `/start` | POST | Starts a test with `{ size, unit, memory, pattern }` |
| `/stream` | GET | SSE stream of live state and log events |
| `/cancel` | POST | Cancels the running test |

### `/start` Request Body

```json
{
  "size": "512",
  "unit": "mb",
  "memory": "sram",
  "pattern": "random"
}
```

### SSE Event Types

| Type | Payload | Description |
|---|---|---|
| `log` | `{ msg, level }` | Log message (info / success / warning / error) |
| `state` | `{ progress, bytes_tested, total_size, errors, elapsed, eta, write_speed, read_speed, ... }` | Live stats update |
| `done` | — | Test completed or cancelled |
| `ping` | — | Keepalive heartbeat |

--- 

### Configuration
 
Memory default capacities (used when hardware detection is unavailable):
 
| Memory | Default Size |
|---|---|
| SRAM | 256 KB |
| SD Card | 32 GB (or detected via `statvfs`) |
| Flash | 4 MB |
| EEPROM | 256 KB |
 
To change defaults, edit `MEMORY_SIZES` in `memory_testers.py`:
 
```python
MEMORY_SIZES = {
    "sram":   256 * 1024,
    "sdcard": 32 * 1024 * 1024 * 1024,
    "flash":  4  * 1024 * 1024,
    "eeprom": 256 * 1024,
}
```
 
---



##  Extending the Tool

To add a new memory type:

1. Create a new tester class in `memory_testers.py` with a `run(state, log, update, cancel)` method
2. Add it to `MEMORY_SIZES` with its default capacity
3. Register it in `detect_memory()` and `run_test()` in `app.py`
4. Add a `<option>` in the memory `<select>` in `index.html`



---

## License

This project is made for the Educational Purpose , For any query Contact...!

---



<div align="center">

Made by [Deepak Chavan](https://github.com/deepakchavan18) & [Gummakonda Bhanu](https://github.com/Gummakondabhanu)

⭐ Star this repo if you found it useful!

</div>
