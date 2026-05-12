# Hass Companion

A lightweight Home Assistant companion application for Linux and macOS that communicates via MQTT discovery. It exposes system metrics and user-defined command-based entities to Home Assistant.

Originally created to overcome the lack of solutions like [HASS.Agent](https://www.hass-agent.io/2.0/) for Linux. Designed to be simple, extensible, and effective.

## Features

- **MQTT Discovery**: Works out of the box with HA's MQTT integration — no manual entity configuration needed
- **Single MQTT Connection**: All entities share one client for efficiency and reliability
- **Cross-Platform**: Runs on Linux and macOS with platform-aware defaults
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

## CLI Interface

```
hass-companion [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to configuration file (default: `config.yaml`) |
| `--validate` | Validate config and exit (exit 0 = valid, exit 1 = errors) |
| `--dry-run` | Create entities without connecting to MQTT, print summary and exit |
| `--log-level LEVEL` | Set logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |
| `--version` | Print version and exit |

### Examples

```bash
# Run with default config.yaml
hass-companion

# Run with a custom config path
hass-companion --config /etc/hass-companion/config.yaml

# Validate configuration without starting
hass-companion --validate --config /etc/hass-companion/config.yaml

# Preview what entities would be created
hass-companion --dry-run

# Run with debug logging
hass-companion --log-level DEBUG
```

## Installation

### Requirements

- Python 3.12+
- An MQTT broker (e.g., Mosquitto) connected to Home Assistant

### pipx (Recommended)

`pipx` installs the application in an isolated environment and makes the `hass-companion` command available on your PATH.

```bash
git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
pipx install .
```

After installation, `hass-companion` is available as a command:

```bash
hass-companion --version
```

### Platform-Specific Install

#### Ubuntu / Debian

```bash
sudo apt update
sudo apt install python3-pip pipx
pipx ensurepath  # adds ~/.local/bin to PATH (restart shell after)

git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
pipx install .
```

#### Fedora

```bash
sudo dnf install python3-pip pipx
pipx ensurepath

git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
pipx install .
```

#### Arch Linux

```bash
sudo pacman -S python-pipx
pipx ensurepath

git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
pipx install .
```

#### NixOS

NixOS users should use the declarative NixOS module for installation and service management. See the [NixOS Module](#nixos-module) section below for full instructions.

To run the package directly without installing as a service:

```bash
# Run directly via flake
nix run github:mhentschke/hass_companion -- --config /path/to/config.yaml

# Or install to profile
nix profile install github:mhentschke/hass_companion
```

#### macOS

```bash
brew install pipx
pipx ensurepath

git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
pipx install .
```

### Virtual Environment (Alternative)

If you prefer not to use pipx:

```bash
git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/hass-companion --version
```

## Service Setup

### CLI Service Commands (Linux & macOS)

The `hass-companion service` subcommand automates service installation. It detects your platform and generates the appropriate service definition.

```
hass-companion service install [--user] [--config PATH]
hass-companion service uninstall [--user]
hass-companion service status
```

| Subcommand | Description |
|------------|-------------|
| `install` | Generate and install the service definition |
| `uninstall` | Stop, disable, and remove the service |
| `status` | Check if the service is installed, enabled, and running |

| Flag | Description |
|------|-------------|
| `--user` | Install as a user-level service (Linux only, uses `~/.config/systemd/user/`) |
| `--config PATH` | Path to config.yaml to embed in the service definition |

#### System-level install (Linux, requires root)

```bash
sudo hass-companion service install --config /etc/hass-companion/config.yaml
```

This creates `/etc/systemd/system/hass-companion.service`, runs `systemctl daemon-reload`, and prints enable/start instructions.

#### User-level install (Linux, no root needed)

```bash
hass-companion service install --user --config ~/.config/hass-companion/config.yaml
```

This creates `~/.config/systemd/user/hass-companion.service`.

#### macOS install

```bash
hass-companion service install --config /usr/local/etc/hass-companion/config.yaml
```

This creates `~/Library/LaunchAgents/com.hass-companion.plist` and loads it via `launchctl`.

#### Uninstall

```bash
# Linux system-level
sudo hass-companion service uninstall

# Linux user-level
hass-companion service uninstall --user

# macOS
hass-companion service uninstall
```

#### Check status

```bash
hass-companion service status
```

Reports whether the service is installed, enabled, and currently running. Exits with code 1 if not installed.

#### NixOS note

On NixOS, `hass-companion service install` is intentionally blocked. NixOS users should use the declarative NixOS module instead (see below).

### NixOS Module

The project provides a NixOS module that declaratively installs hass-companion and runs it as a systemd service.

#### Flake-based usage

Add hass-companion as a flake input and import the module:

```nix
# flake.nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    hass-companion.url = "github:mhentschke/hass_companion";
  };

  outputs = { nixpkgs, hass-companion, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        hass-companion.nixosModules.default
        ./configuration.nix
      ];
    };
  };
}
```

Then in your NixOS configuration:

```nix
# configuration.nix
{
  services.hass-companion = {
    enable = true;
    configFile = ./hass-companion/config.yaml;
    environmentFile = "/run/secrets/hass-companion-env";  # e.g., sops-nix or agenix path
    logLevel = "INFO";
    watchConfig = true;
  };
}
```

#### Non-flake usage (fetchTarball)

For traditional NixOS configurations without flakes:

```nix
# configuration.nix
let
  hass-companion = builtins.fetchTarball {
    url = "https://github.com/mhentschke/hass_companion/archive/main.tar.gz";
    # Replace with actual hash after first build:
    # sha256 = "...";
  };
in
{
  imports = [ "${hass-companion}/nix/module.nix" ];

  services.hass-companion = {
    enable = true;
    configFile = /etc/hass-companion/config.yaml;
    environmentFile = /etc/hass-companion/.env;
  };
}
```

#### Module Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | bool | `false` | Enable the hass-companion service |
| `package` | package | built from source | The hass-companion package to use |
| `configFile` | path | — (required) | Path to the hass-companion `config.yaml` |
| `environmentFile` | path or null | `null` | Path to environment file with MQTT credentials (`.env`, sops-nix secret, etc.) |
| `logLevel` | enum | `"INFO"` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `watchConfig` | bool | `false` | Watch config file for changes and reload automatically |

When enabled, the module creates a systemd service with:
- `After=network-online.target` (waits for network)
- `Restart=on-failure` with 10s delay
- `EnvironmentFile` loaded when `environmentFile` is set
- `--watch-config` flag passed when `watchConfig` is true

### Manual Service Setup

If you prefer not to use the CLI commands, template service files are available in the `contrib/` directory.

#### systemd (Linux)

```bash
sudo cp contrib/hass-companion.service /etc/systemd/system/
# Edit ExecStart path and config path as needed
sudo systemctl daemon-reload
sudo systemctl enable --now hass-companion
```

#### launchd (macOS)

```bash
cp contrib/com.hass-companion.plist ~/Library/LaunchAgents/
# Edit ProgramArguments path and config path as needed
launchctl load ~/Library/LaunchAgents/com.hass-companion.plist
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
      device: my_peripheral
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
# Install dev dependencies
pip install -e ".[dev]"

# Run unit + integration tests
pytest tests/unit tests/integration -v

# Run with coverage
pytest tests/unit tests/integration --cov

# Lint
ruff check .
ruff format --check .

# Run with debug logging
hass-companion --log-level DEBUG
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development setup instructions.

## License

MIT
