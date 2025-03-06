import json
import os
import shutil
import subprocess
from datetime import datetime

from pheonix import app_db
from pheonix.types import AppStatus, PreprocessorResult

APPLET_NAME = "system_load"


def main():
    app = app_db.get_app_by_name(APPLET_NAME)

    temperature = get_temperature()
    load1, load5, load15 = get_cpu_load()
    mem_total, mem_available = get_memory_info()
    disk_total, disk_free = get_disk_usage()
    uptime = get_uptime()
    throttled = get_throttled()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "timestamp": now,
        "temperature": temperature,
        "cpu_load": {"1min": load1, "5min": load5, "15min": load15},
        "memory": {"total_MB": mem_total, "available_MB": mem_available},
        "disk": {"total_MB": disk_total, "free_MB": disk_free},
        "uptime": uptime,
        "throttled": throttled,
    }

    app.data_file.write_text(json.dumps(data))

    if temperature > 80 or mem_available < 200:
        return PreprocessorResult(data, AppStatus.PRIORITIZE, priority=50)

    return PreprocessorResult(data)


def get_temperature():
    """
    Get the current temperature of the Raspberry Pi.
    """
    try:
        output = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
        # Expected output format: "temp=48.0'C\n"
        return float(output.stdout.split("=")[1].split("'")[0])
    except Exception:
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
    Retrieve memory information from /proc/meminfo.
    Returns total and available memory in MB.
    """
    mem_info = {}
    try:
        with open("/prqoc/meminfo", "r") as f:
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
    """
    output = subprocess.run("uptime", shell=True, capture_output=True, text=True)
    return output.stdout.strip().split(",")[0].split("up ")[1].strip()


def get_throttled():
    """
    Get the throttled status of the Raspberry Pi.
    """
    try:
        output = subprocess.run(
            "vcgencmd get_throttled", shell=True, capture_output=True, text=True
        )
        return output.stdout.strip().split("=")[1].strip()
    except Exception:
        return "N/A"


if __name__ == "__main__":
    main()
