import subprocess
import re

ping_time_regex = re.compile(r"time=([\d.]+) ms")
ping_packet_loss_regex = re.compile(r"([\d.]+)% packet loss")


def ping(host, interface = None, size = None, timeout = None):
    command = ["ping"]
    if interface is not None:
        command += ["-I", interface]
    if size is not None:
        command += ["-s", str(size)]
    if timeout is not None:
        command += ["-W", str(timeout)]

    command += ["-c", "1"]
    command += [host]
    return parse_ping(subprocess.run(command, stdout=subprocess.PIPE).stdout.decode("utf-8"))


def parse_ping(result):

    result = result.split("\n")
    result_dict = {}
    try:
        ping_time = float(ping_time_regex.search(result[1]).group(1))
        result_dict["time"] = ping_time
    except AttributeError:
        print("Ping failed")
    ping_packet_loss = float(ping_packet_loss_regex.search(result[-3]).group(1))
    result_dict["packet_loss"] = ping_packet_loss
    return result_dict

if __name__ == "__main__":
    print(ping("8.8.8.8"))