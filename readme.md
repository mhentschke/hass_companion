# Hass Companion

A lightweight Home Assistant companion application for Linux that communicates via MQTT discovery. It exposes system metrics and user-defined command-based entities to Home Assistant.

Originally created to overcome the lack of solutions like [HASS.Agent](https://www.hass-agent.io/2.0/) for Linux. Designed to be simple, extensible, and effective.

## Features

- **MQTT Discovery**: Works out of the box with HA's MQTT integration — no manual entity configuration needed
- **Single MQTT Connection**: All entities share one client for efficiency and reliability
- **Sensors**: Execute commands and expose output as sensor values with optional parser pipelines
- **Binary Sensors**: Command-based with boolean enforcement
- **Switches**: ON/OFF commands with optional state feedback via polling
- **Buttons**: Fire-and-forget command execution
- **Selects**: Dropdown with state map, command template, and optional feedback sensor
- **System Monitoring** (via psutil):
  - CPU usage and frequency (total + per-core)
  - Memory (virtual + swap)
  - Disk usage and IO (total + per-disk, with rates)
  - Network IO (total + per-NIC, with rates)
  - Temperatures and fans
  - Ping and DNS latency
  - Process monitoring (by regex pattern) with control buttons
- **Smart Filtering**: Auto-filters NixOS bind mounts, virtual NICs, and container interfaces
- **Sub-Devices**: Optionally organize system entities into child devices (CPU, Memory, Storage, Network, Sensors)
- **Entity Categories**: Per-core/per-disk/per-NIC entities marked as diagnostic (hidden from default HA views)
- **Discovery Cleanup**: Removes ghost entities from persistent MQTT brokers on restart
- **Async Architecture**: Fully async via asyncio — no threading
- **MQTT Reconnection**: Exponential backoff with automatic state republishing
- **Graceful Shutdown**: Clean SIGTERM/SIGINT handling

## Install

### Quick Install

```bash
git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
./hass-companion.sh install
```

This installs Python dependencies into a venv and offers options to register as a systemd service.

### Manual Install

Requirements: Python 3.12+

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
```

For development:
```bash
.venv/bin/pip install -e ".[dev]"
```

## Configuration

### 1. Create `.env` with MQTT credentials

```env
HA_MQTT_HOST="mqtt_broker_host"
HA_MQTT_PORT=1883
HA_MQTT_USERNAME="mqtt_user"
HA_MQTT_PASSWORD="mqtt_pass"
```

### 2. Create `config.yaml`

```yaml
mqtt:
  host: ${HA_MQTT_HOST}
  port: ${HA_MQTT_PORT}
  username: ${HA_MQTT_USERNAME}
  password: ${HA_MQTT_PASSWORD}
  clean_start: true          # Remove stale discovery on startup (default: false)

hass:
  device_name: My Linux PC
  device_id: my_linux_pc
  sub_devices: true          # Organize system entities into child devices (default: false)

devices:                     # Allows you to configure custom devices for grouping your entities
  my_peripheral:
    name: My Peripheral

entities:
  sensors:
    - name: User Running
      id: user_running
      type: command
      command: "whoami"
      polling_interval: 10

  selects:
    - name: Power Profile
      id: power_profile
      device: my_peripheral  # match the key for the device to group this device into the custom devices
      command_template: "powerprofilesctl set {}"
      state_map:
        Balanced: balanced
        Performance: performance
        "Power Saver": power-saver
      sensor:
        type: command
        command: "powerprofilesctl get"
        polling_interval: 5

  system:
    cpu:
      percent:
        total: true
        per_cpu: true
      freq:
        total: true
        per_cpu: true
    memory:
      virtual: {}
      swap: {}
    storage:
      usage:
        filters:
          include: ["/dev/nvme", "/dev/sda"]
      io:
        total: true
        per_disk: true
        rates: true
        counters: true
        filters:
          include: ["sda", "nvme0n1"]
    network:
      io:
        total: true
        per_nic: true
        rates: true
        filters:
          exclude: ["^veth", "^docker", "^br-"]
    sensors:
      temperatures: {}
      fans: {}
```

### 3. Run

```bash
.venv/bin/python hass-companion.py
```

Or with the launch script:
```bash
./hass-companion.sh start
```

## Configuration Reference

### `mqtt`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | `localhost` | MQTT broker host |
| `port` | int | `1883` | MQTT broker port |
| `username` | string | — | MQTT username |
| `password` | string | — | MQTT password |
| `clean_start` | bool | `false` | Remove all existing discovery messages for this device on startup |

### `hass`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `device_name` | string | required | Default HA device name |
| `device_id` | string | required | Default HA device identifier |
| `sub_devices` | bool | `false` | Create child devices per system category (CPU, Memory, Storage, Network, Sensors) |

### Entity Types

#### Sensors
```yaml
- name: string                    # Display name in HA (required)
  id: string                      # Unique ID (defaults to sanitized name)
  type: command                   # Entity type (default: command)
  command: string                 # Shell command to execute
  shell: bash                     # Shell to use (default: bash)
  polling_interval: float         # Seconds between polls (default: 10)
  command_timeout: float          # Subprocess timeout in seconds (default: 30)
  device: string                  # Optional device key reference
  device_class: string            # Optional HA device class
  unit_of_measurement: string     # Optional unit (enables line graphs in HA)
  icon: string                    # Optional MDI icon
  parse: []                       # Optional parser pipeline
```

#### Binary Sensors
Same fields as Sensors. Final parsed value must be boolean.

#### Switches
```yaml
- name: string                    # Display name in HA (required)
  id: string                      # Unique ID (defaults to sanitized name)
  command_on: string              # Command to turn on (required)
  command_off: string             # Command to turn off (required)
  shell: bash                     # Shell to use (default: bash)
  command_timeout: float          # Subprocess timeout in seconds (default: 30)
  device: string                  # Optional device key reference
  icon: string                    # Optional MDI icon
  binary_sensor:                  # Optional state feedback
    type: command
    command: string
    polling_interval: float
    command_timeout: float
    parse:
      - type: bool
```

#### Buttons
```yaml
- name: string                    # Display name in HA (required)
  id: string                      # Unique ID (defaults to sanitized name)
  command: string                 # Command to execute on press (required)
  shell: bash                     # Shell to use (default: bash)
  device: string                  # Optional device key reference
  icon: string                    # Optional MDI icon
```

#### Selects
```yaml
- name: string                    # Display name in HA (required)
  id: string                      # Unique ID (defaults to sanitized name)
  command_template: string        # Format string with {} placeholder (required)
  shell: bash                     # Shell to use (default: bash)
  state_map:                      # Display value -> command value mapping
    "Display Name": command_value
  device: string                  # Optional device key reference
  icon: string                    # Optional MDI icon
  sensor:                         # Optional state feedback
    type: command
    command: string
    polling_interval: float
    command_timeout: float
```

### System Entities

System entities use smart defaults for filtering:
- **Disk usage**: Only real block devices (`/dev/*`), deduplicates bind mounts
- **Network per-NIC**: Excludes virtual interfaces (veth, docker, virbr, lo, macvtap)

Override with explicit `filters.include` / `filters.exclude` (regex patterns).

### Parser Pipeline

Applied in order to command output:
```yaml
parse:
  - type: regex
    regex: "pattern"
    group: 1
  - type: int | float | bool | string
  - type: compare
    operator: "> | < | >= | <= | == | !="
    value: any
  - type: state_map
    map:
      key: value
```

## Architecture

```
config.yaml + .env
       │
       ▼
┌──────────────────┐
│ Config (Pydantic)│  Validate, resolve env vars
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Shared MQTT      │  Single paho-mqtt client
│ Client           │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Entity Factory   │  Create entities from config
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Async Entity Tasks (asyncio.gather)     │
│  ├── Sensors (CommandFetcher poll loop) │
│  ├── System (SystemFetcher poll loop)   │
│  ├── Interactive (command queue + poll) │
│  └── Reconnection Manager               │
└─────────────────────────────────────────┘
```

## Development

```bash
# Run tests
.venv/bin/pytest tests/unit tests/integration -v

# Run with debug logging
LOG_LEVEL=DEBUG .venv/bin/python hass-companion.py
```

## License

MIT
