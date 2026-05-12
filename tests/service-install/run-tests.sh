#!/bin/bash
# Run service installation tests across multiple distributions.
# Requires Docker with privileged container support.
#
# Usage: ./tests/service-install/run-tests.sh [distro...]
# Examples:
#   ./tests/service-install/run-tests.sh              # Run all distros
#   ./tests/service-install/run-tests.sh ubuntu       # Run only Ubuntu
#   ./tests/service-install/run-tests.sh ubuntu fedora # Run Ubuntu and Fedora

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NETWORK="service-install_default"
ALL_DISTROS=("ubuntu" "fedora")
DISTROS=("${@:-${ALL_DISTROS[@]}}")

TOTAL_PASS=0
TOTAL_FAIL=0

cleanup() {
    echo ""
    echo "=== Cleanup ==="
    for distro in "${ALL_DISTROS[@]}"; do
        docker rm -f "hass-companion-test-${distro}" 2>/dev/null || true
    done
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" down 2>/dev/null || true
}

trap cleanup EXIT

echo "=== Starting MQTT Broker ==="
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d --wait
echo "Broker ready."
echo ""

for distro in "${DISTROS[@]}"; do
    echo "============================================"
    echo "=== Testing: $distro ==="
    echo "============================================"
    echo ""

    IMAGE="hass-companion-test-${distro}"
    CONTAINER="hass-companion-test-${distro}"

    # Remove any leftover container
    docker rm -f "$CONTAINER" 2>/dev/null || true

    # Build
    echo "Building $distro image..."
    if ! docker build -f "$SCRIPT_DIR/Dockerfile.${distro}" -t "$IMAGE" "$PROJECT_ROOT" 2>&1 | tail -5; then
        echo "  ✗ Build failed for $distro"
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
        continue
    fi
    echo ""

    # Start container with systemd as PID 1
    echo "Starting $distro container with systemd..."
    docker run -d \
        --name "$CONTAINER" \
        --privileged \
        --cgroupns=host \
        --network "$NETWORK" \
        -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
        -e MQTT_HOST=mosquitto \
        -e MQTT_PORT=1883 \
        -e HA_MQTT_HOST=mosquitto \
        -e HA_MQTT_PORT=1883 \
        "$IMAGE" >/dev/null

    # Wait for systemd to boot
    echo "Waiting for systemd to boot..."
    for i in $(seq 1 15); do
        if docker exec "$CONTAINER" systemctl is-system-running --wait 2>/dev/null | grep -qE "running|degraded"; then
            break
        fi
        sleep 1
    done
    echo ""

    # Run tests
    echo "Running tests..."
    echo ""
    if docker exec -e MQTT_HOST=mosquitto -e MQTT_PORT=1883 -e HA_MQTT_HOST=mosquitto -e HA_MQTT_PORT=1883 \
        "$CONTAINER" /test-service.sh; then
        TOTAL_PASS=$((TOTAL_PASS + 1))
    else
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
    fi

    # Stop container
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo ""
done

echo "============================================"
echo "=== Final Summary ==="
echo "  Distros passed: $TOTAL_PASS"
echo "  Distros failed: $TOTAL_FAIL"
echo "============================================"

if [ $TOTAL_FAIL -gt 0 ]; then
    exit 1
fi
