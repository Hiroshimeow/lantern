"""System & GPU/VRAM Telemetry module for Lantern (Issue 1).

Provides lightweight, cached real-time GPU/VRAM (NVIDIA nvidia-smi, AMD rocm-smi)
and system RAM/CPU telemetry without external mandatory dependencies.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time
from typing import Any

_CACHE_LOCK = threading.Lock()
_CACHED_STATS: dict[str, Any] | None = None
_CACHE_TS: float = 0.0
_CACHE_TTL_SEC: float = 3.0


def _query_nvidia_smi() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe and platform.system() == "Windows":
        candidate = r"C:\Windows\System32\nvidia-smi.exe"
        if os.path.isfile(candidate):
            exe = candidate
    if not exe:
        return []
    try:
        cmd = [
            exe,
            "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": 1.8,
            " encoding": "utf-8",
            "errors": "replace",
        }
        kwargs.pop(" encoding", None)
        kwargs["encoding"] = "utf-8"
        if platform.system() == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(cmd, **kwargs)
        if res.returncode != 0 or not res.stdout.strip():
            return []
        gpus: list[dict[str, Any]] = []
        for raw_line in res.stdout.strip().splitlines():
            parts = [p.strip() for p in raw_line.split(",")]
            if len(parts) < 4:
                continue
            try:
                idx = int(parts[0])
            except ValueError:
                idx = len(gpus)
            name = parts[1]
            try:
                used_mb = float(parts[2])
            except ValueError:
                used_mb = 0.0
            try:
                total_mb = float(parts[3])
            except ValueError:
                total_mb = 0.0
            try:
                util_pct = float(parts[4]) if len(parts) > 4 else 0.0
            except ValueError:
                util_pct = 0.0
            try:
                temp_c = float(parts[5]) if len(parts) > 5 else None
            except ValueError:
                temp_c = None
            pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
            gpus.append(
                {
                    "index": idx,
                    "vendor": "NVIDIA",
                    "name": name,
                    "vramUsedMb": round(used_mb, 1),
                    "vramTotalMb": round(total_mb, 1),
                    "vramUsedGb": round(used_mb / 1024.0, 2),
                    "vramTotalGb": round(total_mb / 1024.0, 2),
                    "vramPercent": pct,
                    "gpuUtilPercent": round(util_pct, 1),
                    "temperatureC": temp_c,
                }
            )
        return gpus
    except Exception:
        return []


def _query_system_memory() -> dict[str, Any]:
    try:
        if platform.system() == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_mb = stat.ullTotalPhys / (1024 * 1024)
            avail_mb = stat.ullAvailPhys / (1024 * 1024)
            used_mb = max(0.0, total_mb - avail_mb)
            return {
                "ramUsedMb": round(used_mb, 1),
                "ramTotalMb": round(total_mb, 1),
                "ramUsedGb": round(used_mb / 1024.0, 2),
                "ramTotalGb": round(total_mb / 1024.0, 2),
                "ramPercent": round(float(stat.dwMemoryLoad), 1),
            }
        if os.path.exists("/proc/meminfo"):
            info: dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    num = v.strip().split()[0]
                    if num.isdigit():
                        info[k.strip()] = int(num)
            total_kb = info.get("MemTotal", 0)
            avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
            used_kb = max(0, total_kb - avail_kb)
            total_mb = total_kb / 1024.0
            used_mb = used_kb / 1024.0
            pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
            return {
                "ramUsedMb": round(used_mb, 1),
                "ramTotalMb": round(total_mb, 1),
                "ramUsedGb": round(used_mb / 1024.0, 2),
                "ramTotalGb": round(total_mb / 1024.0, 2),
                "ramPercent": pct,
            }
    except Exception:
        pass
    return {
        "ramUsedMb": 0.0,
        "ramTotalMb": 0.0,
        "ramUsedGb": 0.0,
        "ramTotalGb": 0.0,
        "ramPercent": 0.0,
    }


def get_system_telemetry(force: bool = False) -> dict[str, Any]:
    global _CACHED_STATS, _CACHE_TS
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force and _CACHED_STATS is not None and (now - _CACHE_TS) < _CACHE_TTL_SEC:
            return _CACHED_STATS

    gpus = _query_nvidia_smi()
    mem = _query_system_memory()
    cpu_count = os.cpu_count() or 1
    load_1m = None
    try:
        if hasattr(os, "getloadavg"):
            load_1m = round(os.getloadavg()[0], 2)
    except Exception:
        load_1m = None

    primary_gpu = gpus[0] if gpus else None
    payload: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "cpu": {
            "cores": cpu_count,
            "load1m": load_1m,
        },
        "memory": mem,
        "gpus": gpus,
        "hasGpu": bool(gpus),
        "primaryGpu": primary_gpu,
    }
    with _CACHE_LOCK:
        _CACHED_STATS = payload
        _CACHE_TS = now
    return payload
