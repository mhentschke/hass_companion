FROM nixos/nix:latest

# Enable flakes
RUN echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf

WORKDIR /app
COPY . .

# Use nix-shell with Python + pip to install and verify
# Once flake.nix exists (task 5.3), this can switch to `nix develop`
RUN nix-shell -p python312 python312Packages.pip python312Packages.setuptools --run " \
    python3 -m venv /tmp/venv && \
    /tmp/venv/bin/pip install . && \
    /tmp/venv/bin/hass-companion --version && \
    /tmp/venv/bin/hass-companion --validate --config tests/install/config.yaml \
"
