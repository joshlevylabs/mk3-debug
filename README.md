# MK3 Amplifier Network Diagnostic Tool

A standalone diagnostic utility for troubleshooting Sonance MK3 amplifier network issues. Discovers amplifiers on your local network, tests connectivity, and runs diagnostic commands — no installation or technical setup required.

## Download

**[Download the latest release](https://github.com/joshlevylabs/mk3-debug/releases/latest)**

| Platform | File | Size |
|----------|------|------|
| **Windows 10/11** | `MK3_Diagnostic_Tool_Windows.exe` | ~30 MB |
| **macOS 12+** | `MK3_Diagnostic_Tool_macOS.zip` | ~35 MB |
| **Linux** | `MK3_Diagnostic_Tool_Linux` | ~30 MB |

## Installation

### Windows
1. Download `MK3_Diagnostic_Tool_Windows.exe` from the [Releases page](https://github.com/joshlevylabs/mk3-debug/releases/latest)
2. Double-click to run
3. If Windows SmartScreen appears, click **"More info"** then **"Run anyway"**

### macOS
1. Download `MK3_Diagnostic_Tool_macOS.zip` from the [Releases page](https://github.com/joshlevylabs/mk3-debug/releases/latest)
2. Unzip the file
3. Double-click `MK3_Diagnostic_Tool` to launch
4. If macOS blocks the app: go to **System Settings > Privacy & Security** and click **"Open Anyway"**

### Linux
1. Download `MK3_Diagnostic_Tool_Linux` from the [Releases page](https://github.com/joshlevylabs/mk3-debug/releases/latest)
2. Make it executable: `chmod +x MK3_Diagnostic_Tool_Linux`
3. Run: `./MK3_Diagnostic_Tool_Linux`

## What It Does

- **Network Discovery** — Finds MK3 amplifiers on your network using mDNS/Bonjour
- **Connectivity Testing** — Verifies TCP connections to amplifier control port (52000)
- **DNS & Hostname Resolution** — Checks that amplifiers are resolvable by name
- **Diagnostic Commands** — Sends commands to amplifiers and displays real-time status
- **Diagnostic Reports** — Generates reports to share with support teams

## Supported Amplifiers

- DSP 8-130 MK3
- DSP 2-750 MK3
- DSP 2-150 MK3

## Requirements

- Your computer must be on the **same network** as the MK3 amplifiers
- Amplifiers must be powered on and connected via Ethernet
- No additional software installation is needed — the tool is fully self-contained

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No amplifiers found | Verify your computer is on the same subnet as the amplifiers |
| Connection timeout | Check that port 52000 is not blocked by a firewall |
| macOS won't open the app | System Settings > Privacy & Security > Open Anyway |
| Windows SmartScreen warning | Click "More info" > "Run anyway" |

## Building From Source

If you prefer to build from source:

```bash
git clone https://github.com/joshlevylabs/mk3-debug.git
cd mk3-debug
pip install -r requirements.txt
python build.py --clean
```

The executable will be in the `dist/` folder.

---

**Author:** Joshua Levy — Lead Electronics Test Engineer, Sonance
**Version:** 1.1.0
