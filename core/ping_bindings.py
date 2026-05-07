import logging
import re
import subprocess

from core.platform import current_platform

logger = logging.getLogger(__name__)

ping_time_regex = re.compile(r"time=([\d.]+) ms")
ping_packet_loss_regex = re.compile(r"([\d.]+)% packet loss")


def ping(host, interface=None, size=None, timeout=None):
    command = current_platform.build_ping_command(
        host,
        timeout=timeout or 5.0,
        interface=interface,
        size=size,
    )
    return parse_ping(subprocess.run(command, stdout=subprocess.PIPE).stdout.decode("utf-8"))


def parse_ping(result):

    result = result.split("\n")
    result_dict = {}
    try:
        ping_time = float(ping_time_regex.search(result[1]).group(1))
        result_dict["time"] = ping_time
    except AttributeError:
        logger.warning("Ping failed for host")
    ping_packet_loss = float(ping_packet_loss_regex.search(result[-3]).group(1))
    result_dict["packet_loss"] = ping_packet_loss
    return result_dict


if __name__ == "__main__":
    print(ping("8.8.8.8"))
