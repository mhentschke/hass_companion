import logging
import re
import subprocess

from core.platform import current_platform

logger = logging.getLogger(__name__)

dns_lookup_regex = re.compile(r"Query time: ([\d.]+) msec")


def dig(host):
    command = current_platform.build_dns_command(host)
    return parse_dig(subprocess.run(command, stdout=subprocess.PIPE).stdout.decode("utf-8"))


def parse_dig(result):
    result = result.split("\n")
    dns_lookup_time = float(dns_lookup_regex.search(result[-6]).group(1))
    return {"resolution_time": dns_lookup_time}


if __name__ == "__main__":
    print(dig("google.com"))
