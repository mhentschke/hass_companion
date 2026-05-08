{
  lib,
  python312Packages,
}:

python312Packages.buildPythonApplication rec {
  pname = "hass-companion";
  version = "0.1.0";
  pyproject = true;

  src = lib.cleanSource ../.;

  build-system = with python312Packages; [
    setuptools
  ];

  dependencies = with python312Packages; [
    bidict
    ha-mqtt-discoverable
    paho-mqtt
    pydantic
    python-dotenv
    pyyaml
    psutil
  ];

  nativeCheckInputs = with python312Packages; [
    pytestCheckHook
    pytest-asyncio
    pytest-mock
  ];

  # Only run unit and integration tests (smoke tests require Docker)
  pytestFlags = [ "-v" ];
  enabledTestPaths = [
    "tests/unit"
    "tests/integration"
  ];

  meta = with lib; {
    description = "A lightweight Home Assistant companion for Linux/macOS via MQTT discovery";
    license = licenses.mit;
    maintainers = [ ];
    mainProgram = "hass-companion";
  };
}
