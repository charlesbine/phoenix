"""Gather CPU/memory/disk/temperature stats. Primarily useful on Raspberry Pi."""

import json
import os
import shutil
import subprocess
from datetime import datetime

from phoenix.models import AppStatus, PreprocessorResult
from phoenix.paths import data_path
from phoenix.settings import Settings


def run(settings: Settings) -> PreprocessorResult:
    temperature = _get_temperature()
    load1, load5, load15 = _get_cpu_load()
    mem_total, mem_available = _get_memory_info()
    disk_total, disk_free = _get_disk_usage()
    uptime = _get_uptime()
    throttled = _get_throttled()

    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "temperature": temperature,
        "cpu_load": {"1min": load1, "5min": load5, "15min": load15},
        "memory": {"total_MB": mem_total, "available_MB": mem_available},
        "disk": {"total_MB": disk_total, "free_MB": disk_free},
        "uptime": uptime,
        "throttled": throttled,
    }

    data_path("system_load").write_text(json.dumps(data))

    if (isinstance(temperature, float) and temperature > 80) or (
        isinstance(mem_available, int) and mem_available < 200
    ):
        return PreprocessorResult(data, AppStatus.PRIORITIZE, priority=50)

    return PreprocessorResult(data)


def _get_temperature() -> float | str:
    try:
        out = subprocess.run(
            ["vcgencmd", "measure_temp"], capture_output=True, text=True, check=False
        )
        return float(out.stdout.split("=")[1].split("'")[0])
    except Exception:
        return "N/A"


def _get_cpu_load() -> tuple[float, float, float]:
    try:
        return os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)


def _get_memory_info() -> tuple[int, int]:
    try:
        mem_info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) >= 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    mem_info[key] = int(value)
        return mem_info.get("MemTotal", 0) // 1024, mem_info.get("MemAvailable", 0) // 1024
    except Exception:
        return (0, 0)


def _get_disk_usage() -> tuple[int, int]:
    usage = shutil.disk_usage("/")
    return usage.total // (1024 * 1024), usage.free // (1024 * 1024)


def _get_uptime() -> str:
    try:
        out = subprocess.run(["uptime"], capture_output=True, text=True, check=False)
        return out.stdout.strip().split(",")[0].split("up ")[1].strip()
    except Exception:
        return "N/A"


def _get_throttled() -> str:
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, check=False
        )
        return out.stdout.strip().split("=")[1].strip()
    except Exception:
        return "N/A"
