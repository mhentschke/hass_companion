#!/bin/bash
# This script runs inside a container with systemd as PID 1.
# Invoked via: docker exec <container> /test-service.sh
set -euo pipefail

PASS=0
FAIL=0
MQTT_HOST="${MQTT_HOST:-mosquitto}"
MQTT_PORT="${MQTT_PORT:-1883}"

pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

echo "=== Service Installation Test ==="
echo "Distribution: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
echo ""

# --- Test 1: Binary is accessible ---
echo "[1] Binary accessibility"
if hass-companion --version >/dev/null 2>&1; then
    pass "hass-companion binary found and runs"
else
    fail "hass-companion binary not found or fails"
fi

# --- Test 2: Validate config ---
echo "[2] Config validation"
export HA_MQTT_HOST="$MQTT_HOST"
export HA_MQTT_PORT="$MQTT_PORT"
if hass-companion --validate --config /etc/hass-companion/config.yaml 2>&1; then
    pass "Config validates successfully"
else
    fail "Config validation failed"
fi

# --- Test 3: Service install (system-level) ---
echo "[3] Service install (system-level)"
if hass-companion service install --config /etc/hass-companion/config.yaml 2>&1; then
    pass "Service install command succeeded"
else
    fail "Service install command failed"
fi

# --- Test 4: Unit file exists and content is correct ---
echo "[4] Unit file verification"
UNIT_FILE="/etc/systemd/system/hass-companion.service"
if [ -f "$UNIT_FILE" ]; then
    pass "Unit file created at $UNIT_FILE"
else
    fail "Unit file not found at $UNIT_FILE"
fi

if grep -q "ExecStart=.*hass-companion.*--config.*/etc/hass-companion/config.yaml" "$UNIT_FILE" 2>/dev/null; then
    pass "ExecStart contains correct binary and config path"
else
    fail "ExecStart line incorrect"
    cat "$UNIT_FILE" 2>/dev/null || true
fi

if grep -q "Restart=on-failure" "$UNIT_FILE" 2>/dev/null; then
    pass "Restart policy set to on-failure"
else
    fail "Restart policy missing"
fi

if grep -q "After=network-online.target" "$UNIT_FILE" 2>/dev/null; then
    pass "After=network-online.target present"
else
    fail "After=network-online.target missing"
fi

if grep -q "WantedBy=multi-user.target" "$UNIT_FILE" 2>/dev/null; then
    pass "WantedBy=multi-user.target present"
else
    fail "WantedBy=multi-user.target missing"
fi

# --- Test 5: Enable and start the service ---
echo "[5] Enable and start service"
# Inject env vars into the service (systemd won't read .env automatically)
mkdir -p /etc/systemd/system/hass-companion.service.d
cat > /etc/systemd/system/hass-companion.service.d/env.conf <<EOF
[Service]
EnvironmentFile=/etc/hass-companion/.env
EOF
systemctl daemon-reload

if systemctl enable hass-companion 2>&1; then
    pass "Service enabled"
else
    fail "Service enable failed"
fi

if systemctl start hass-companion 2>&1; then
    pass "Service started"
else
    fail "Service start failed"
    journalctl -u hass-companion --no-pager -n 20
fi

# Give it a moment to connect and publish
sleep 3

# --- Test 6: Service is running ---
echo "[6] Service running check"
if systemctl is-active --quiet hass-companion; then
    pass "Service is active (running)"
else
    fail "Service is not running"
    systemctl status hass-companion --no-pager || true
    journalctl -u hass-companion --no-pager -n 30
fi

# --- Test 7: MQTT discovery message ---
echo "[7] MQTT discovery message"
# ha-mqtt-discoverable uses PascalCase with hyphens for topic paths
DISCOVERY_MSG=$(timeout 10 mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -t "homeassistant/sensor/Service-Test-Device/Echo-Sensor/config" \
    -C 1 -W 8 2>/dev/null || true)

if [ -n "$DISCOVERY_MSG" ]; then
    pass "MQTT discovery message received"
    if echo "$DISCOVERY_MSG" | grep -q '"Echo Sensor"'; then
        pass "Discovery payload contains entity name 'Echo Sensor'"
    else
        fail "Discovery payload missing expected entity name"
        echo "  Got: $DISCOVERY_MSG"
    fi
else
    fail "No MQTT discovery message received"
    journalctl -u hass-companion --no-pager -n 20
fi

# --- Test 8: MQTT state message ---
echo "[8] MQTT state message"
STATE_MSG=$(timeout 10 mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -t "hmd/sensor/Service-Test-Device/Echo-Sensor/state" \
    -C 1 -W 8 2>/dev/null || true)

if [ -n "$STATE_MSG" ]; then
    STATE_VAL=$(echo "$STATE_MSG" | tr -d '[:space:]')
    if [ "$STATE_VAL" = "42" ]; then
        pass "State message received with correct value: 42"
    else
        pass "State message received (value: '$STATE_VAL')"
    fi
else
    fail "No MQTT state message received"
    journalctl -u hass-companion --no-pager -n 20
fi

# --- Test 9: Service survives restart ---
echo "[9] Service restart survival"
systemctl restart hass-companion
sleep 4

if systemctl is-active --quiet hass-companion; then
    pass "Service survived restart"
else
    fail "Service did not survive restart"
    journalctl -u hass-companion --no-pager -n 20
fi

# Verify MQTT still works after restart
STATE_AFTER=$(timeout 10 mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -t "hmd/sensor/Service-Test-Device/Echo-Sensor/state" \
    -C 1 -W 8 2>/dev/null || true)

if [ -n "$STATE_AFTER" ]; then
    pass "MQTT state still published after restart"
else
    fail "No MQTT state after restart"
    journalctl -u hass-companion --no-pager -n 20
fi

# --- Test 10: Service status command ---
echo "[10] CLI status command"
STATUS_OUT=$(hass-companion service status 2>&1)
if echo "$STATUS_OUT" | grep -q "installed"; then
    pass "CLI status reports installed"
else
    fail "CLI status doesn't report installed"
    echo "  Got: $STATUS_OUT"
fi

if echo "$STATUS_OUT" | grep -q "running"; then
    pass "CLI status reports running"
else
    fail "CLI status doesn't report running"
fi

# --- Test 11: Duplicate install blocked ---
echo "[11] Duplicate install protection"
DUP_OUT=$(hass-companion service install --config /etc/hass-companion/config.yaml 2>&1 || true)
if echo "$DUP_OUT" | grep -qi "already installed"; then
    pass "Duplicate install correctly blocked"
else
    fail "Duplicate install not blocked"
    echo "  Got: $DUP_OUT"
fi

# --- Test 12: Service uninstall ---
echo "[12] Service uninstall"
if hass-companion service uninstall 2>&1; then
    pass "Service uninstall command succeeded"
else
    fail "Service uninstall command failed"
fi

if [ ! -f "$UNIT_FILE" ]; then
    pass "Unit file removed after uninstall"
else
    fail "Unit file still exists after uninstall"
fi

if ! systemctl is-active --quiet hass-companion 2>/dev/null; then
    pass "Service stopped after uninstall"
else
    fail "Service still running after uninstall"
fi

# --- Test 13: Status after uninstall ---
echo "[13] Status after uninstall"
if hass-companion service status 2>&1; then
    fail "Status should exit non-zero when not installed"
else
    pass "Status exits non-zero when not installed"
fi

# --- Summary ---
echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "SOME TESTS FAILED"
    exit 1
else
    echo "ALL TESTS PASSED"
    exit 0
fi
