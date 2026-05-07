FROM nixos/nix:latest

# Enable flakes
RUN echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf

WORKDIR /app
COPY . .

# Use nix-shell with Python + pip to install and verify
RUN nix-shell -p python312 python312Packages.pip python312Packages.setuptools --run " \
    python3 -m venv /tmp/venv && \
    /tmp/venv/bin/pip install . && \
    /tmp/venv/bin/hass-companion --version && \
    printf 'mqtt:\n  host: localhost\n  port: 1883\nhass:\n  device_name: Test\n  device_id: test\n' > /tmp/test-config.yaml && \
    /tmp/venv/bin/hass-companion --validate --config /tmp/test-config.yaml \
"
