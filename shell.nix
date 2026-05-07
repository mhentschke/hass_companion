# Standalone shell.nix for users without flakes enabled.
# Provides the same development environment as the flake devShell.
# Usage: nix-shell
{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312;
  pythonPkgs = python.pkgs;
in
pkgs.mkShell {
  name = "hass-companion-dev";

  packages = [
    python
    pythonPkgs.pip
    pythonPkgs.setuptools

    # Runtime dependencies
    pythonPkgs.bidict
    pythonPkgs.paho-mqtt
    pythonPkgs.pydantic
    pythonPkgs.python-dotenv
    pythonPkgs.pyyaml
    pythonPkgs.psutil

    # Dev dependencies
    pythonPkgs.pytest
    pythonPkgs.pytest-asyncio
    pythonPkgs.pytest-cov
    pythonPkgs.pytest-mock
    pkgs.ruff
  ];

  shellHook = ''
    echo "Hass Companion dev shell — Python ${python.version}"
    echo "Run: pip install -e . to install in editable mode"
    echo "Run: pytest to run tests"
  '';
}
