# A Home Assistant Companion

Hass Companion was created initially to overcome the lack of solutions like [HASS.Agent](https://www.hass-agent.io/2.0/) for Linux. It is a lightweight alternative that can be easily extended to support more features. There is currently no reason it would not work on Windows but Hass.Agent probably provides more features and a friendlier experience out-of-the-box. Hass Companion is designed to be a simple and effective solution for Linux users.
# Features

- **MQTT Discovery**: Hass Companion communicates with Home Assistant via MQTT. Discovery works out of the box without additional setup as long as you have MQTT integration configured in HA
- **Switches**:
  - **Command**: Execute a command when switch turns on and another when it turns off. Optionally, you can also monitor a third command to check the status of the switch.
- **Sensors**:
  - **Command**: Execute a command and return the output as sensor value.
- **Binary Sensors**:
  - **Command**: Execute a command and return the output as binary sensor value.
- **Buttons**:
  - **Command**: Execute a command.


# Install

#### 1) Clone the Repository or download the zip and go to the repository folder in your terminal
``` 
git clone https://github.com/mhentschke/hass_companion.git 
cd hass_companion
```

## Quick Install

Run ```./hass-companion.sh install```. This will install python, all of the dependencies of the project into a venv and offer you options to register it as a service for auto start 

## Manual Install

### Requirements
- **Python** > 3.12.3 (older 3.X versions will probably work but are not tested)

### Install Dependencies

#### 1) Install Python requirements:

```
pip install -r requirements.txt
```

### Configure

#### 1) Create .env file containing your MQTT information:
```
HA_MQTT_HOST="host_ip_or_url"
HA_MQTT_PORT=1883
HA_MQTT_USERNAME="username"
HA_MQTT_PASSWORD="password"
```
* Port is optional and defaults to 1833
* Username and Password are optional and depend on your MQTT config. Having authentication is recommended

#### 2) Create your config file
An example of config file is provided with the code. Your config file needs to be called ```config.yaml```

#### 3) Test your configuration
Run ```python hass-companion.py``` and check the output for any errors. If none are present, you are good to configure Hass Companion to start with your system

#### 4) Start with system

Run ```./hass-companion.sh autostart```



# Todo
- **Notifications**
- **Lights**: Possible integration with OpenRGB
- **System Monitoring**
  - **CPU Metrics**
  - **Memory Metrics**
  - **Disk Metrics**
  - **Network Metrics**
  - **GPU Metrics**
  - **Application Monitoring**
  - **Webcam**
  - **Microphone**: Mostly whether it is being used or not and by which application
- **Custom Scripts**: ability to write python scripts to extend functionality without changing the main code
- **Security Improvements**
- **Documentation Improvements**





# Configuration

## MQTT Settings

Ensure that you're using the same MQTT instance as configured in Home Assistant by utilizing environment variables throughout this file. It is recommended to create your own .env file in the same directory as the hass-companion.py. That will get loaded automatically and can be used anywher you want in your config.

```yaml
mqtt:
  host: ${HA_MQTT_HOST}
  port: ${HA_MQTT_PORT}
  username: ${HA_MQTT_USERNAME}
  password: ${HA_MQTT_PASSWORD}
```

## Device Settings

The companion will use the default device for any entity that does not specify a device. You can override this by setting a different device in your configuration.

### Default Device Configuration

```yaml
hass:
  device_name: "Default Device"
  device_id: "default_device_id"
```

### Additional Devices
You can add additional devices to the companion by specifying them in the `devices` section of the configuration file. Each device should have a unique name and ID.

```yaml
devices:
  device_id:
    name: "Device Name"
```

## Entity Settings

Entities are configured under the `entities` section. Each entity can specify its own device, or it will use the default device if none is specified.

```yaml
entities:
  sensors:
    ...
  binary_sensors:
    ...
  switches:
    ...
  selects:
    ... # Not Implemented Yet
```

### Sensors
Sensors can be either numeric or string. If a numeric sensor does not have a unit of measurement, it will still not show as a line graph in Home assistant, so addind a unit of measurement is always recommended

```yaml
entities:
  sensors:
    - name: "Sensor Name"
        id: "sensor_id" # Unique identifier for the entity
        type: "command" # Type of the sensor (e.g., command)
        device: "device_id" # Optional
        unit_of_measurement: "Unit" # Optional, but recommended for numeric sensors
        parse: # Optional, can be used to process the output of a command
          - type: "regex" # Type of parsing (e.g., regex)
            regex: "pattern" # Regex pattern to match the output
            group: 1 # Group number or name to extract from the regex match
          - type: "int" # Convert to integer
          - type: "float" # Convert to float
          - type: "str" # Convert to string
          - type: "bool" # Convert to boolean
          - type: "compare" # Compare with a value
            value: 10 # Value to compare with
            operator: ">" # Operator to use for comparison (e.g., >, <, ==)
```

### Binary Sensors
Binary sensors can be either on or off. They are typically used to represent a state, such as whether a something is running or not.

```yaml
entities:
  binary_sensors:
    - name: "Binary Sensor Name"
      id: "sensor_id"
      type: "command" # Type of the sensor (e.g., command)
      device: "device_id" # Optional
      parse:
        - type: "bool" # This is mandatory as a last parse step for binary sensors
```

### Buttons
A button can only be pressed and has no intrinsid state. Its purpose is to do something without monitoring the effect of that action.

```yaml
entities:
  buttons:
    - name: Button Name
      id: button_id
      command: "some command to be executed"
      shell: "bash" # currently supported shells: bash
```

### Switches
Switches can be turned on or off. They are typically used to control devices, such as turning lights on and off. They also have an optional binary_sensor which can be configured the same way as any other binary_sensor, with the exception that the binary_sensor id will be ignored. This is not an actual Home Assistant binary_sensor and it is only used to determine the state of the switch

```yaml
entities:
  switches:
    - name: "Switch Name"
      id: "switch_id" # Unique identifier for the entity
      type: "command" # Type of the sensor (e.g., command)
      command_on: "on_command" # Command to turn on the switch
      command_off: "off_command" # Command to turn off the switch
      shell: "bash" # Currently supported options are: Bash
      device: "device_id" # Optional
      binary_sensor: # Optional
        type: "command"
        command: "status_command"
        shell: "bash"
        polling_rate: 1 # Polling rate in 1/seconds
        parse: # Mandatory conversion to bool
          - type: "bool"
```

### Selects
Selects can be in a list of states. They can be used to control multiple power profiles for example.

```yaml
entities:
  selects:
    - name: "Select Name"
      id: "select_id" # Unique identifier for the entity
      type: "command" # Type of the sensor (e.g., command)
      command_template: "echo {} > /my/file" # Command template to be executed when a state is selected. This is a python f string and will be formated as such.
      state_map:
        # Value to be displayed in Home Assistant: Value to be passed to command
        State1: "Value1"
        State2: "Value2"
      sensor: # Optional
        type: "command" # Type of the sensor (e.g., command)
        command: "cat /my/file" # Command to read the current state from a file
        polling_rate: 1 # Polling rate in 1/seconds

