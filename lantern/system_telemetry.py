"""System & GPU/VRAM/CPU/Temperature Telemetry module for Lantern v7.92.

Provides lightweight, cached real-time GPU/VRAM (NVIDIA nvidia-smi, AMD rocm-smi / sysfs,
Windows GPU counters), CPU utilization %, system RAM, and CPU/GPU temperature (°C)
across both Linux and Windows without external mandatory dependencies.
"""
from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_CACHE_LOCK = threading.Lock()
_CACHED_STATS: dict[str, Any] | None = None
_CACHE_TS: float = 0.0
_CACHE_TTL_SEC: float = 2.5

_CPU_LOCK = threading.Lock()
_LAST_CPU_TOTAL: int = 0
_LAST_CPU_IDLE: int = 0
_LAST_CPU_PCT: float = 0.0


def _find_nvidia_smi() -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    if platform.system() == "Windows":
        candidates = [
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        try:
            matches = glob.glob(r"C:\Windows\System32\DriverStore\FileRepository\nv*\nvidia-smi.exe")
            if matches:
                return matches[0]
        except Exception:
            pass
    else:
        for c in (
            "/usr/bin/nvidia-smi",
            "/usr/local/bin/nvidia-smi",
            "/usr/local/cuda/bin/nvidia-smi",
            "/usr/lib/wsl/lib/nvidia-smi",
        ):
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
    return None


def _parse_float_metric(raw: str) -> float | None:
    cleaned = raw.strip().replace("%", "")
    if not cleaned or cleaned.lower() in {"n/a", "[not supported]", "none", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _query_nvidia_smi() -> list[dict[str, Any]]:
    exe = _find_nvidia_smi()
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
            "encoding": "utf-8",
            "errors": "replace",
        }
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
            name = parts[1] or f"NVIDIA GPU {idx}"
            used_mb = _parse_float_metric(parts[2]) or 0.0
            total_mb = _parse_float_metric(parts[3]) or 0.0
            util_pct = (_parse_float_metric(parts[4]) if len(parts) > 4 else None) or 0.0
            temp_c = _parse_float_metric(parts[5]) if len(parts) > 5 else None
            if temp_c is not None:
                temp_c = round(temp_c, 1)
            pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
            gpus.append(
                {
                    "index": idx,
                    "vendor": "NVIDIA",
                    "name": name,
                    "available": True,
                    "vramUsedMb": round(used_mb, 1),
                    "vramTotalMb": round(total_mb, 1),
                    "vramUsedGb": round(used_mb / 1024.0, 2),
                    "vramTotalGb": round(total_mb / 1024.0, 2),
                    "vramPercent": pct,
                    "gpuUtilPercent": round(util_pct, 1),
                    "utilPercent": round(util_pct, 1),
                    "temperatureC": temp_c,
                    "tempC": temp_c,
                }
            )
        return gpus
    except Exception:
        return []


def _query_linux_drm_gpus() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    if platform.system() != "Linux":
        return gpus
    try:
        for card_dir in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
            if "-" in card_dir.name:
                continue
            dev = card_dir / "device"
            vram_tot_file = dev / "mem_info_vram_total"
            vram_used_file = dev / "mem_info_vram_used"
            if not vram_tot_file.is_file() or not vram_used_file.is_file():
                continue
            try:
                total_bytes = int(vram_tot_file.read_text(encoding="utf-8").strip())
                used_bytes = int(vram_used_file.read_text(encoding="utf-8").strip())
            except Exception:
                continue
            if total_bytes <= 0:
                continue
            total_mb = total_bytes / (1024.0 * 1024.0)
            used_mb = used_bytes / (1024.0 * 1024.0)
            util_pct = 0.0
            busy_file = dev / "gpu_busy_percent"
            if busy_file.is_file():
                try:
                    util_pct = float(busy_file.read_text(encoding="utf-8").strip())
                except Exception:
                    util_pct = 0.0
            temp_c: float | None = None
            for temp_file in dev.glob("hwmon/hwmon*/temp1_input"):
                try:
                    raw_t = int(temp_file.read_text(encoding="utf-8").strip())
                    if raw_t > 1000:
                        temp_c = round(raw_t / 1000.0, 1)
                        break
                except Exception:
                    continue
            pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
            gpus.append(
                {
                    "index": len(gpus),
                    "vendor": "AMD/DRM",
                    "name": f"DRM {card_dir.name}",
                    "available": True,
                    "vramUsedMb": round(used_mb, 1),
                    "vramTotalMb": round(total_mb, 1),
                    "vramUsedGb": round(used_mb / 1024.0, 2),
                    "vramTotalGb": round(total_mb / 1024.0, 2),
                    "vramPercent": pct,
                    "gpuUtilPercent": round(util_pct, 1),
                    "utilPercent": round(util_pct, 1),
                    "temperatureC": temp_c,
                    "tempC": temp_c,
                }
            )
    except Exception:
        pass
    return gpus


def _read_cpu_times() -> tuple[int, int] | None:
    if platform.system() == "Windows":
        try:
            import ctypes

            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]

            idle_ft = FILETIME()
            kernel_ft = FILETIME()
            user_ft = FILETIME()
            if ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle_ft), ctypes.byref(kernel_ft), ctypes.byref(user_ft)
            ):
                idle = (idle_ft.dwHighDateTime << 32) | idle_ft.dwLowDateTime
                kernel = (kernel_ft.dwHighDateTime << 32) | kernel_ft.dwLowDateTime
                user = (user_ft.dwHighDateTime << 32) | user_ft.dwLowDateTime
                total = kernel + user
                return total, idle
        except Exception:
            return None
    if os.path.exists("/proc/stat"):
        try:
            with open("/proc/stat", "r", encoding="utf-8", errors="ignore") as f:
                first = f.readline()
            if first.startswith("cpu "):
                parts = [int(x) for x in first.split()[1:] if x.isdigit()]
                if len(parts) >= 4:
                    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                    total = sum(parts)
                    return total, idle
        except Exception:
            return None
    return None


def _query_cpu_percent(cpu_count: int, load_1m: float | None) -> float:
    global _LAST_CPU_TOTAL, _LAST_CPU_IDLE, _LAST_CPU_PCT
    sample1 = _read_cpu_times()
    if sample1 is not None:
        with _CPU_LOCK:
            prev_total, prev_idle = _LAST_CPU_TOTAL, _LAST_CPU_IDLE
            if prev_total == 0:
                _LAST_CPU_TOTAL, _LAST_CPU_IDLE = sample1
                time.sleep(0.025)
                sample2 = _read_cpu_times()
                if sample2 is not None:
                    prev_total, prev_idle = sample1
                    sample1 = sample2
            total, idle = sample1
            delta_total = total - prev_total
            delta_idle = idle - prev_idle
            _LAST_CPU_TOTAL, _LAST_CPU_IDLE = total, idle
            if delta_total > 0:
                busy = max(0, delta_total - delta_idle)
                _LAST_CPU_PCT = round(min(100.0, max(0.0, (busy / delta_total) * 100.0)), 1)
                return _LAST_CPU_PCT
            if _LAST_CPU_PCT > 0:
                return _LAST_CPU_PCT
    if load_1m is not None and cpu_count > 0:
        return round(min(100.0, max(0.0, (load_1m / float(cpu_count)) * 100.0)), 1)
    return 0.0


def _query_cpu_temperature() -> float | None:
    if platform.system() == "Linux":
        preferred: list[float] = []
        fallback: list[float] = []
        try:
            for zdir in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
                tfile = zdir / "temp"
                if not tfile.is_file():
                    continue
                try:
                    raw = float(tfile.read_text(encoding="utf-8").strip())
                    val = raw / 1000.0 if raw > 200 else raw
                    if not (5.0 <= val <= 130.0):
                        continue
                    ztype = ""
                    type_file = zdir / "type"
                    if type_file.is_file():
                        ztype = type_file.read_text(encoding="utf-8", errors="ignore").strip().lower()
                    if any(k in ztype for k in ("pkg", "cpu", "core", "k10", "soc", "Tctl".lower())):
                        preferred.append(val)
                    else:
                        fallback.append(val)
                except Exception:
                    continue
            for hdir in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
                name_file = hdir / "name"
                hname = ""
                if name_file.is_file():
                    try:
                        hname = name_file.read_text(encoding="utf-8", errors="ignore").strip().lower()
                    except Exception:
                        pass
                for tfile in sorted(hdir.glob("temp*_input")):
                    try:
                        raw = float(tfile.read_text(encoding="utf-8").strip())
                        val = raw / 1000.0 if raw > 200 else raw
                        if not (5.0 <= val <= 130.0):
                            continue
                        if any(k in hname for k in ("coretemp", "k10temp", "zenpower", "cpu", "acpitz")):
                            preferred.append(val)
                        else:
                            fallback.append(val)
                    except Exception:
                        continue
        except Exception:
            pass
        if preferred:
            return round(max(preferred), 1)
        if fallback:
            return round(max(fallback), 1)
    elif platform.system() == "Windows":
        try:
            kwargs: dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "timeout": 1.2,
                "encoding": "utf-8",
                "errors": "replace",
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            }
            res = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance -Namespace root/CIMV2 -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty HighPrecisionTemperature)",
                ],
                **kwargs,
            )
            if res.returncode == 0 and res.stdout.strip():
                raw_k = float(res.stdout.strip().splitlines()[0].strip())
                # HighPrecisionTemperature is in tenths of Kelvin (e.g. 3182 -> 318.2K -> 45.0C)
                temp_c = (raw_k / 10.0) - 273.15 if raw_k > 1000 else raw_k - 273.15
                if 5.0 <= temp_c <= 130.0:
                    return round(temp_c, 1)
        except Exception:
            pass
    return None


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
            pct = round(float(stat.dwMemoryLoad), 1)
            return {
                "ramUsedMb": round(used_mb, 1),
                "ramTotalMb": round(total_mb, 1),
                "ramUsedGb": round(used_mb / 1024.0, 2),
                "ramTotalGb": round(total_mb / 1024.0, 2),
                "ramPercent": pct,
                "usedMb": round(used_mb, 1),
                "totalMb": round(total_mb, 1),
                "usedGb": round(used_mb / 1024.0, 2),
                "totalGb": round(total_mb / 1024.0, 2),
                "percent": pct,
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
                "usedMb": round(used_mb, 1),
                "totalMb": round(total_mb, 1),
                "usedGb": round(used_mb / 1024.0, 2),
                "totalGb": round(total_mb / 1024.0, 2),
                "percent": pct,
            }
    except Exception:
        pass
    return {
        "ramUsedMb": 0.0,
        "ramTotalMb": 0.0,
        "ramUsedGb": 0.0,
        "ramTotalGb": 0.0,
        "ramPercent": 0.0,
        "usedMb": 0.0,
        "totalMb": 0.0,
        "usedGb": 0.0,
        "totalGb": 0.0,
        "percent": 0.0,
    }


def get_system_telemetry(force: bool = False) -> dict[str, Any]:
    global _CACHED_STATS, _CACHE_TS
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force and _CACHED_STATS is not None and (now - _CACHE_TS) < _CACHE_TTL_SEC:
            return _CACHED_STATS

    gpus = _query_nvidia_smi()
    if not gpus:
        gpus = _query_linux_drm_gpus()
    mem = _query_system_memory()
    cpu_count = os.cpu_count() or 1
    load_1m = None
    try:
        if hasattr(os, "getloadavg"):
            load_1m = round(os.getloadavg()[0], 2)
    except Exception:
        load_1m = None

    cpu_pct = _query_cpu_percent(cpu_count, load_1m)
    cpu_temp = _query_cpu_temperature()

    primary_gpu = gpus[0] if gpus else None
    gpu_temp = primary_gpu.get("tempC") if primary_gpu else None
    effective_temp = gpu_temp if gpu_temp is not None else cpu_temp

    gpu_summary: dict[str, Any] = (
        dict(primary_gpu)
        if primary_gpu
        else {
            "available": False,
            "name": "System Integrated",
            "vendor": "",
            "vramUsedMb": 0.0,
            "vramTotalMb": 0.0,
            "vramUsedGb": 0.0,
            "vramTotalGb": 0.0,
            "vramPercent": 0.0,
            "gpuUtilPercent": 0.0,
            "utilPercent": 0.0,
            "temperatureC": effective_temp,
            "tempC": effective_temp,
        }
    )
    if gpu_summary.get("tempC") is None and effective_temp is not None:
        gpu_summary["tempC"] = effective_temp
        gpu_summary["temperatureC"] = effective_temp

    payload: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "cpu": {
            "cores": cpu_count,
            "load1m": load_1m,
            "loadPercent": cpu_pct,
            "tempC": cpu_temp,
        },
        "memory": mem,
        "ram": mem,
        "gpu": gpu_summary,
        "gpus": gpus,
        "hasGpu": bool(gpus),
        "primaryGpu": primary_gpu,
        "tempC": effective_temp,
    }
    with _CACHE_LOCK:
        _CACHED_STATS = payload
        _CACHE_TS = now
    return payload
