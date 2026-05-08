{
  description = "Hass Companion — Home Assistant MQTT Companion for Linux/macOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    (flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        pythonPkgs = python.pkgs;
      in
      {
        packages.default = pkgs.callPackage ./nix/package.nix {};

        devShells.default = pkgs.mkShell {
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
        };
      }
    )) // {
      # NixOS module (system-independent, outside eachDefaultSystem)
      # nixosModules.default = import ./nix/module.nix;
    };
}
