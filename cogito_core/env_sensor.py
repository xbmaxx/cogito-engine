"""
env_sensor.py —— 环境传感器。

收集系统环境信息：时间、系统状态。
跨平台版本 —— 无 Hermes 依赖，无 macOS 特定 API。

对原始 consciousness_env/env_sensor.py 的平台无关替代。
"""

from __future__ import annotations

import logging
import os
import platform
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── 时间传感器 ──

def _sense_time() -> Dict[str, Any]:
    """获取当前时间信息。"""
    now = datetime.now().astimezone()
    hour = now.hour
    if hour < 5:
        period = "凌晨"
    elif hour < 9:
        period = "清晨"
    elif hour < 12:
        period = "上午"
    elif hour < 14:
        period = "中午"
    elif hour < 18:
        period = "下午"
    elif hour < 21:
        period = "傍晚"
    else:
        period = "深夜"

    return {
        "iso": now.isoformat(),
        "weekday": now.strftime("%A"),
        "period": period,
        "local": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": str(now.tzinfo),
        "hour": hour,
    }


# ── 系统信息传感器 ──

def _sense_system() -> Dict[str, Any]:
    """获取系统信息（跨平台）。"""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    uname = platform.uname()

    return {
        "os": uname.system,
        "os_release": uname.release,
        "os_version": uname.version,
        "machine": uname.machine,
        "hostname": hostname,
        "python_version": platform.python_version(),
        "processor": uname.processor or platform.processor() or "unknown",
    }


# ── CPU/内存传感器 ──

def _sense_resources() -> Dict[str, Any]:
    """获取 CPU 和内存使用情况（跨平台）。"""
    result: Dict[str, Any] = {"cpu_count": os.cpu_count() or 0}

    # CPU 使用率（最佳尝试）
    try:
        import psutil
        result["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        result["memory_total_gb"] = round(mem.total / (1024 ** 3), 1)
        result["memory_available_gb"] = round(mem.available / (1024 ** 3), 1)
        result["memory_percent"] = mem.percent
    except ImportError:
        result["cpu_percent"] = -1

    return result


# ── 电池传感器（跨平台，最佳尝试） ──

def _sense_battery() -> Dict[str, Any]:
    """获取电池信息。"""
    result: Dict[str, Any] = {"available": False}
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is not None:
            result["available"] = True
            result["percent"] = battery.percent
            result["power_plugged"] = battery.power_plugged
            result["time_left_minutes"] = (
                round(battery.secsleft / 60, 1)
                if battery.secsleft > 0
                else -1
            )
            result["status"] = (
                "充电中" if battery.power_plugged else "电池供电"
            )
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("电池信息获取失败: %s", exc)

    return result


# ── 天气传感器（需高德 API Key） ──

def _sense_weather() -> Dict[str, Any]:
    """获取天气信息（需要高德地图 API Key）。

    通过环境变量 AMAP_API_KEY 配置。
    """
    result: Dict[str, Any] = {"available": False}
    api_key = os.environ.get("AMAP_API_KEY", "")
    if not api_key:
        return result

    # 默认城市（可通过环境变量或 IP 定位配置）
    city = os.environ.get("COGITO_WEATHER_CITY", "北京")

    try:
        import urllib.request
        import json

        # 高德天气 API
        url = (
            f"https://restapi.amap.com/v3/weather/weatherInfo"
            f"?key={api_key}&city={city}&extensions=base"
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("status") == "1" and data.get("lives"):
            live = data["lives"][0]
            result["available"] = True
            result["city"] = live.get("city", city)
            result["weather"] = live.get("weather", "")
            result["temperature"] = live.get("temperature", "")
            result["wind_direction"] = live.get("winddirection", "")
            result["wind_power"] = live.get("windpower", "")
            result["humidity"] = live.get("humidity", "")
            result["report_time"] = live.get("reporttime", "")
    except ImportError:
        logger.debug("urllib 不可用，无法查询天气")
    except Exception as exc:
        logger.debug("天气查询失败: %s", exc)

    return result


# ── 主入口 ──

def get_snapshot(
    include_weather: bool = False,
    include_battery: bool = True,
    include_resources: bool = True,
) -> Optional[str]:
    """获取环境快照文本。

    Args:
        include_weather: 是否包含天气（需要 API Key）
        include_battery: 是否包含电池信息
        include_resources: 是否包含 CPU/内存信息

    Returns:
        环境快照文本，或 None（全部传感器不可用时）
    """
    try:
        time_data = _sense_time()
    except Exception:
        time_data = {}

    if not time_data:
        return None

    now_local = time_data.get("local", datetime.now().strftime("%H:%M"))
    period = time_data.get("period", "未知")
    weekday = time_data.get("weekday", "")
    hour = time_data.get("hour", 0)

    parts = [f"🕐 {now_local} · {weekday} {period} (hour={hour})"]

    # 系统信息
    try:
        sys_data = _sense_system()
        parts.append(
            f"💻 {sys_data['os']} {sys_data['os_release']} "
            f"({sys_data['machine']}) Python {sys_data['python_version']}"
        )
    except Exception:
        pass

    # 资源
    if include_resources:
        try:
            res = _sense_resources()
            if res.get("cpu_percent", -1) >= 0:
                parts.append(f"🖥 CPU {res['cpu_percent']}% · 核心 {res['cpu_count']}")
            else:
                parts.append(f"🖥 核心数 {res['cpu_count']}")
            if "memory_total_gb" in res:
                parts.append(
                    f"💾 内存 {res['memory_available_gb']}GB / "
                    f"{res['memory_total_gb']}GB ({res['memory_percent']}%)"
                )
        except Exception:
            pass

    # 电池
    if include_battery:
        try:
            batt = _sense_battery()
            if batt.get("available"):
                batt_str = f"🔋 {batt['status']} {batt['percent']}%"
                if batt.get("time_left_minutes", -1) > 0:
                    batt_str += f" · 剩余 {batt['time_left_minutes']:.0f} 分钟"
                parts.append(batt_str)
        except Exception:
            pass

    # 天气
    if include_weather:
        try:
            weather = _sense_weather()
            if weather.get("available"):
                parts.append(
                    f"🌤 {weather['city']} {weather['weather']} "
                    f"{weather['temperature']}°C "
                    f"湿度 {weather['humidity']}%"
                )
        except Exception:
            pass

    return "\n".join(parts)
