import subprocess
import threading
from bidict import bidict
from . import parsers

class Sensor():
    def __init__(self, result_callback):
        self.result_callback = result_callback
    def update(self, value):
        self.result_callback(value)
    def stop(self):
        pass
    

class OptimisticSensor(Sensor):
    def __init__(self):
        self.state = None
        def null_function(value):
            pass
        super().__init__(null_function)
    def update(self, value):
        self.state = value

class BinarySensor(Sensor):
    def update(self, value):
        if isinstance(value, bool):
            super().update(value)
        else:
            raise ValueError('Invalid binary sensor value')
    def on(self):
        self.update(True)
    def off(self):
        self.update(False)

class PollingSensor(Sensor):
    def __init__(self, function, polling_rate, result_callback):
        self.function = function
        self.polling_rate = polling_rate
        self.polling_time = 1.0/polling_rate
        self.exit = threading.Event()
        self.thread = threading.Thread(target = self.polling_thread, daemon = True)
        super().__init__(result_callback)
        self.start()
    
    def start(self):
        self.thread.start()
    
    def polling_thread(self):
        while not self.exit.is_set():
            self.update(self.function())
            self.exit.wait(timeout = self.polling_time)
    
    def pre_process_result(self, result):
        return result # This is a placeholder function that returns the raw result. You can modify it in subclasses to preprocess the result as needed.

    def update(self, value):
        self.result_callback(self.pre_process_result(value))

    def stop(self):
        self.exit.set()

class MultiSensor(Sensor):
    def __init__(self, function, result_callbacks):
        self.result_callbacks = result_callbacks
        Sensor.__init__(self, self.result_callback_unwrapper)

    def result_callback_unwrapper(self, values, callbacks = None):
        if callbacks is None:
            callbacks = self.result_callbacks
        if isinstance(values, int) or isinstance(values, float) or isinstance(values, bool) or isinstance(values, str):
            callbacks(values)
        if isinstance(values, list):
            for callback, value in zip(callbacks, values):
                self.result_callback_unwrapper(value, callbacks=callback) # recursive call
        elif isinstance(values, dict):
            for keys in values.keys():
                self.result_callback_unwrapper( values[keys], callbacks = callbacks[keys]) # recursive call
        elif isinstance(values, tuple):
            if isinstance(callbacks, dict):
                self.result_callback_unwrapper(values._asdict(), callbacks = callbacks)
            else:
                for callback, value in zip(callbacks, values):
                    self.result_callback_unwrapper(value, callbacks = callback)

class MultiPollingSensor(MultiSensor, PollingSensor):
    def __init__(self, function, polling_rate, result_callbacks):
        MultiSensor.__init__(self, function, result_callbacks)
        PollingSensor.__init__(self, function, polling_rate, self.result_callback_unwrapper)

class CommandSensor(Sensor):
    def __init__(self, command, polling_rate, result_callback, shell, parsers = []):
        self.command = command
        self.polling_rate = polling_rate
        self.polling_time = 1.0/polling_rate
        self.exit = threading.Event()
        self.thread = threading.Thread(target = self.polling_thread, daemon = True)
        self.shell = shell
        self.parsers = parsers
        super().__init__(result_callback)
        self.start()

    def start(self):
        print("Starting command sensor")
        self.thread.start()

    def polling_thread(self):
        while not self.exit.is_set():
            # execute command
            self.update(subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", self.command], stdout = subprocess.PIPE).stdout.decode("utf-8"))
            
            # wait for next polling time
            self.exit.wait(timeout = self.polling_time)
    
    def pre_process_result(self, result):
        if isinstance(result, str): # remove trailing newline character from result string
            return(result.rstrip("\n"))

    def update(self, value, raw = False):
        if raw:
            result = value # do not apply parsers to raw values
        else:  # apply parsers to non-raw values
            result = self.pre_process_result(value)
            for p in self.parsers:
                result = p.parse(result) # apply parsers to result
        self.result_callback(result)
        print("Updating Sensor. Raw value: ", value, "Parsed value: ", result)

    def stop(self):
        self.exit.set()

class BinaryCommandSensor(CommandSensor, BinarySensor):
    pass


class Switch:
    def __init__(self, command_on, command_off, shell, sensor = None):
        self.command_on = command_on
        self.command_off = command_off
        self.shell = "bash"
        if sensor is None:
            self.sensor = OptimisticSensor()
        else:
            self.sensor = sensor

    def turn_on(self):
        subprocess.run([self.shell, "-c", self.command_on], stdout=subprocess.PIPE).stdout.decode("utf-8")
        self.sensor.update("True")

    def turn_off(self):
        subprocess.run([self.shell, "-c", self.command_off], stdout=subprocess.PIPE).stdout.decode("utf-8")
        self.sensor.update("False")
    
    def stop(self):
        self.sensor.stop()

class Button:
    def __init__(self, function):
        self.function = function
    
    def press(self):
        self.function()

class CommandButton(Button):
    def __init__(self, command, shell):
        self.command = command
        self.shell = shell
        super().__init__(self.execute_command)
    
    def execute_command(self):
        subprocess.run([self.shell, "-c", self.command], stdout=subprocess.PIPE).stdout.decode("utf-8")


class Select:
    def __init__(self, command_template, shell, state_map: bidict = bidict({}), sensor = None):
        self.command_template = command_template
        self.shell = shell
        self.state_map = state_map
        if sensor is None:
            self.sensor = OptimisticSensor()
        else:
            self.sensor = sensor
        # Add a parser to the sensor that will convert the raw value to the mapped value
        sensor.parsers.append(parsers.StateMapResultParser(state_map.inverse))

    def select(self, value):
        mapped_value  = self.state_map.get(value, value)
        subprocess.run([self.shell, "-c", self.command_template.format(mapped_value)], stdout=subprocess.PIPE).stdout.decode("utf-8")
        self.sensor.update(value, raw = True)
    
    def stop(self):
        self.sensor.stop()