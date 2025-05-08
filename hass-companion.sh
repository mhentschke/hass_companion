#!/bin/bash

# Help function
help() {
    echo "Usage: install.sh <command>"
    echo "Available commands:"
    echo "  start           Starts the application in standalone mode"
    echo "  install         Install the application"
    echo "  uninstall       Uninstall the application"
    echo "  autostart       Set up the application to start on boot"
    echo "  remove-autostart Remove the application from starting on boot"
    echo "  help            Show this help message"
    exit 1
}

start() {
    # ask if should stop the service
    read -p "This will stop the service and run as standalone. To restart the service, you can run ./hass-companion.sh autostart. Are you sure you want to stop the service? (y/n): " stop_service
    if [ "$stop_service" == "y" ]; then
        echo "Stopping service..."
        sudo systemctl stop hass-companion.service
        # get the path to the virtual environment's python interpreter
        python_path=$(which python3)
        # get the path to the script
        script_path=$(pwd)/hass-companion.py
        echo "Starting standalone with command: $python_path $script_path"
        $python_path $script_path
    else
        echo Operation aborted by user!
    fi

}

autostart() {
    # check if the service file already exists
    if [ -f "/etc/systemd/system/hass-companion.service" ]; then
        echo "Autostart service already exists. Skipping file creation."
    else

        # get current user's username
        current_user=$(whoami)
        # get the path to the script
        script_path=$(pwd)/hass-companion.py
        # get the path to the virtual environment's python interpreter
        python_path=$(which python3)
        # create a systemd service file
        echo "Setting up autostart for user $current_user at /etc/systemd/system/hass-companion.service"
        file_contents="[Unit]
    Description=HASS Companion Service
    After=network.target
    [Service]
    User=$current_user
    WorkingDirectory=$(pwd)
    ExecStart=$python_path $script_path
    Restart=always"
        echo Creating Service File:
        echo "$file_contents"
        echo "--- End of contents ---"
        echo "$file_contents" > hass-companion.service
        sudo mv hass-companion.service /etc/systemd/system/
        echo "Reloading systemd daemon..."
        sudo systemctl daemon-reload
    fi
    # enable and start the service
    echo "Enabling and starting the service"
    sudo systemctl enable hass-companion.service
    sudo systemctl start hass-companion.service
}

remove_autostart() {
    # Check if the service exists
    systemctl list-unit-files | grep hass-companion.service > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "Disabling and stopping the service..."
        sudo systemctl disable hass-companion.service
        sudo systemctl stop hass-companion.service
        # ask user if they want to remove the service file
        read -p "Do you want to remove the hass-companion.service file? (y/n): " remove_file
        if [ "$remove_file" == "y" ]; then
           echo "Removing hass-companion.service file..."
           sudo rm /etc/systemd/system/hass-companion.service
           echo "Reloading systemd daemon..."
           sudo systemctl daemon-reload
        fi
    else
        echo "hass-companion.service does not exist."
    fi

}

install() {
    # Install Python 3 and pip
    sudo apt install python3 python3-pip -y

    # create a virtual environment
    python3 -m venv .venv

    # activate the virtual environment
    source .venv/bin/activate

    # install dependencies
    pip install -r requirements.txt

    echo "Installation complete. You can now run python hass-companion.py."

    # ask user if they want to set up a systemd service
    read -p "Do you want to set up a systemd service? This will enable you to run the script at startup (y/n): " setup_service
    if [ "$setup_service" == "y" ]; then
        autostart
    fi
}

uninstall() {
    remove_autostart
    # remove venv
    rm -r .venv

}


# Check if command argument was provided
if [ "$#" -ne 1 ]; then
    help
fi

# Get command from command line. Options are install, uninstall, autostart, remove-autostart and help
command=$1
# Check if command is valid
case $command in
    start)
        start
        ;;
    install)
        echo "Installing..."
        install
        ;;
    uninstall)
        echo "Uninstalling..."
        uninstall
        ;;
    autostart)
        echo "Setting up autostart..."
        autostart
        ;;
    remove-autostart)
        echo "Stopping autostart..."
        remove_autostart
        ;;
    *)
        echo "Invalid Option"
        help
        ;;

esac



