# Contributing to Hass Companion

## Development Setup

### Prerequisites

- Python 3.12+
- Docker (for smoke tests)
- Git

### Clone and Install

```bash
git clone https://github.com/mhentschke/hass_companion.git
cd hass_companion
```

#### Option A: Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### Option B: Nix (with flakes)

```bash
nix develop
pip install -e .
```

#### Option C: Nix (without flakes)

```bash
nix-shell
pip install -e .
```

## Running Tests

### Unit Tests

Fast, no external dependencies:

```bash
pytest tests/unit -v
```

### Integration Tests

Test entity behavior with mocked I/O:

```bash
pytest tests/integration -v
```

### Unit + Integration (with coverage)

```bash
pytest tests/unit tests/integration -v --cov --cov-report=term-missing
```

Coverage threshold is 80% for new code.

### Smoke Tests

Require Docker. These run the full app against a real Mosquitto broker:

```bash
# Start the broker
docker compose -f tests/smoke/docker-compose.yml up -d --wait

# Get the mapped port and run tests
export TEST_MQTT_PORT=$(docker compose -f tests/smoke/docker-compose.yml port mosquitto 1883 | cut -d: -f2)
pytest tests/smoke/ -v

# Tear down
docker compose -f tests/smoke/docker-compose.yml down
```

### Run All Tests (except smoke)

```bash
pytest -m "not smoke"
```

## Lint and Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for lint violations
ruff check .

# Check formatting
ruff format --check .

# Auto-fix lint issues
ruff check . --fix

# Auto-format
ruff format .
```

CI will fail if there are lint violations or formatting issues. Run these checks locally before pushing.

## CI Pipeline

Every push and pull request triggers the following jobs:

| Job | What it does |
|-----|--------------|
| `lint` | Runs `ruff check` and `ruff format --check` |
| `test-linux` | Unit + integration tests on Ubuntu with coverage |
| `test-macos` | Unit + integration tests on macOS |
| `smoke` | Smoke tests with Docker Mosquitto |
| `install-test` | Verifies `pipx install .` works on Ubuntu, Fedora, Arch, and NixOS |

## Project Structure

```
hass_companion/              # Python package (CLI entry point)
├── __init__.py              # Package marker, __version__
├── cli.py                   # argparse CLI (--config, --validate, --dry-run, etc.)
└── main.py                  # Async main() logic

core/                        # Core application logic
├── config.py                # Pydantic config loading and validation
├── discovery.py             # MQTT discovery cleanup
├── factory.py               # Entity factory (creates entities from config)
├── filters.py               # Smart include/exclude filtering (EntityFilter)
├── mqtt.py                  # Shared MQTT client and reconnection manager
├── parsers.py               # Parser pipeline (regex, type cast, compare, state_map)
├── units.py                 # Suffix-based unit resolver
├── subprocess.py            # Async subprocess execution
├── rate.py                  # Rate calculator for IO metrics
├── network_sensors.py       # Ping and DNS sensor implementations
├── ping_bindings.py         # Platform-aware ping command builder
├── dns_bindings.py          # Platform-aware DNS command builder
├── psutil_bindings.py       # psutil wrappers with null guards
├── entities/                # Entity type implementations
│   ├── base.py              # BaseEntity, Entity, CompositeEntity
│   ├── fetcher.py           # StateFetcher (CommandFetcher, SystemFetcher)
│   ├── sensor.py            # CommandSensor, SystemSensor
│   ├── binary_sensor.py     # BinarySensor
│   ├── button.py            # Button
│   ├── switch.py            # Switch (InteractiveEntity)
│   ├── select.py            # Select (InteractiveEntity)
│   ├── interactive.py       # InteractiveEntity base (command queue + feedback)
│   └── system.py            # SystemMultiSensor (psutil → N sensors)
└── platform/                # Platform abstraction layer
    ├── __init__.py           # get_platform(), current_platform singleton
    ├── base.py               # PlatformCommands Protocol
    ├── linux.py              # LinuxPlatform implementation
    └── darwin.py             # DarwinPlatform implementation

tests/
├── unit/                    # Pure logic tests (no I/O)
├── integration/             # Entity behavior with mocked I/O
├── smoke/                   # Full-stack tests with Docker MQTT
└── install/                 # Dockerfiles for distro install verification

contrib/
├── hass-companion.service   # systemd service unit
└── com.hass-companion.plist # macOS launchd plist
```

## Key Concepts

- **Composition over inheritance**: Entities compose a `StateFetcher` for polling rather than inheriting from it
- **Platform abstraction**: OS-specific behavior lives in `core/platform/` — no scattered `platform.system()` checks
- **Single MQTT client**: All entities share one connection via `Settings.MQTT(client=...)`
- **Async throughout**: `asyncio.gather()` runs all entity tasks concurrently
- **Pydantic config**: Validated at startup with clear error messages on failure

## Making Changes

1. Create a branch from `main`
2. Make your changes
3. Run lint and tests locally (`ruff check . && ruff format --check . && pytest tests/unit tests/integration`)
4. Push and open a pull request
5. CI must pass before merge
