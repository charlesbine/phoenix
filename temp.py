"""
Get the current temperature and system metrics of the Raspberry Pi every 1 minute and log them.
By default, logs in JSON format to a file (temp.json) unless --stdout is provided.
"""

import argparse
import json
from datetime import datetime
import os
import time
import shutil
import subprocess


def get_temperature():
    """
    Get the current temperature of the Raspberry Pi.
    """
    try:
        output = os.popen("vcgencmd measure_temp").read()
        # Expected output format: "temp=48.0'C\n"
        return output.split("=")[1].split("'")[0]
    except IndexError:
        return "N/A"


def get_cpu_load():
    """
    Get the system CPU load averages for the past 1, 5, and 15 minutes.
    """
    try:
        load1, load5, load15 = os.getloadavg()
        return load1, load5, load15
    except Exception:
        return (0.0, 0.0, 0.0)


def get_memory_info():
    """
    Retrieve memory information from /p roc/meminfo.
    Returns total and available memory in MB.
    """
    mem_info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) >= 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    mem_info[key] = int(value)
        mem_total = mem_info.get("MemTotal", 0) // 1024  # in MB
        mem_available = mem_info.get("MemAvailable", 0) // 1024  # in MB
        return mem_total, mem_available
    except Exception:
        return (0, 0)


def get_disk_usage():
    """
    Get disk usage statistics of the root filesystem.
    Returns total and free disk space in MB.
    """
    usage = shutil.disk_usage("/")
    total_mb = usage.total // (1024 * 1024)
    free_mb = usage.free // (1024 * 1024)
    return total_mb, free_mb


def get_uptime():
    """
    Get the uptime of the Raspberry Pi.
    use uptime command to get the uptime
    """
    output = subprocess.run("uptime", shell=True, capture_output=True, text=True)
    return output.stdout.strip().split(",")[0].split("up ")[1].strip()


def get_throttled():
    """
    Get the throttled status of the Raspberry Pi.
    use `vcgencmd get_throttled` to get the status
    """
    output = subprocess.run("vcgencmd get_throttled", shell=True, capture_output=True, text=True)
    return output.stdout.strip().split("=")[1].strip()


def main(log_file=None, use_stdout=False, fmt="json"):
    """
    Main function to log the temperature and system metrics.

    If use_stdout is True, logs to stdout.
    Otherwise, writes logs to the provided log_file.

    The output format is determined by fmt, which can be "json" or "text".
    """
    while True:
        temperature = get_temperature()
        load1, load5, load15 = get_cpu_load()
        mem_total, mem_available = get_memory_info()
        disk_total, disk_free = get_disk_usage()
        uptime = get_uptime()
        throttled = get_throttled()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if fmt == "json":
            log_entry = {
                "timestamp": now,
                "temperature": temperature,
                "cpu_load": {"1min": load1, "5min": load5, "15min": load15},
                "memory": {"total_MB": mem_total, "available_MB": mem_available},
                "disk": {"total_MB": disk_total, "free_MB": disk_free},
                "uptime": uptime,
                "throttled": throttled,
            }
            log_line = json.dumps(log_entry)
        else:  # Plain text output
            log_line = (
                f"{now} - Temp: {temperature}°C, "
                f"CPU Load: {load1:.2f}, {load5:.2f}, {load15:.2f}, "
                f"Memory: {mem_available}MB free / {mem_total}MB total, "
                f"Disk: {disk_free}MB free / {disk_total}MB total, "
                f"Uptime: {uptime} seconds, "
                f"Throttled: {throttled}"
            )

        if use_stdout:
            print(log_line)
        else:
            # Also print to stdout for immediate feedback.
            print(log_line)
            with open(log_file, "a") as f:
                f.write(log_line + "\n")
        time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Log Raspberry Pi temperature and system metrics to a file or stdout."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--log-file",
        type=str,
        default="temp.json",
        help="The file to write logs to (default: temp.json)",
    )
    group.add_argument(
        "--stdout", action="store_true", help="Log to stdout instead of writing to a file"
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format: 'json' for JSON format (default) or 'text' for plain text",
    )
    args = parser.parse_args()

    if args.stdout:
        main(use_stdout=True, fmt=args.format)
    else:
        main(log_file=args.log_file, fmt=args.format)
