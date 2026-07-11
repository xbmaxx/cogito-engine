"""
env_sensor.py —— 环境传感器。

收集系统环境信息：时间、系统状态。
跨平台版本 —— 无 Hermes 依赖，无 macOS 特定 API。

对原始 consciousness_env/env_sensor.py 的平台无关替代。
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── 国内 IP 归属查询服务列表 ──
# 优先级从高到低。利用代理软件的 GEOIP CN DIRECT 规则，
# 查询国内服务一定走直连，拿到的就是真实宽带出口 IP。
_IP_LOOKUP_SERVICES = [
    "https://myip.ipip.net",          # 返回 "当前 IP：xxx  来自于：中国 浙江 舟山  移动"
    "https://ip.useragentinfo.com",   # 返回 city/country/isp JSON
    "http://ip.taobao.com/service/getIpInfo.php?ip=myip",  # 阿里 IP 库
]
# 正则：从 myip.ipip.net 响应中提取 省/直辖市、市、运营商
# 格式：中国 <省> <市> <运营商>（运营商可选）
_RE_IPIP = re.compile(
    r"(?:来自于[：:])\s*中国\s+(\S+)\s+(\S+)(?:\s+(\S+))?"
)


# ── 时间传感器 ──

def _sense_time() -> Dict[str, Any]:
    """获取当前时间信息（纯系统时钟，不受代理影响）。"""
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


# ── IP 归属查询 ──

def _query_ip_location(url: str) -> Optional[Dict[str, str]]:
    """调用单个 IP 归属服务，返回 {city, isp} 或 None。"""
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Cogito/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8", errors="replace")

        # ── myip.ipip.net ──
        # "当前 IP：xxx  来自于：中国 浙江 舟山  移动"
        # group(1)=省, group(2)=市, group(3)=运营商（可选）
        m = _RE_IPIP.search(text)
        if m:
            return {"city": m.group(2), "isp": m.group(3) or ""}

        # ── 淘宝 / useragentinfo 等 JSON 格式 ──
        try:
            data = json.loads(text)
            if url.startswith("http://ip.taobao.com"):
                info = data.get("data", {})
                city = info.get("city", "") or info.get("region", "")
                if city:
                    return {"city": city, "isp": info.get("isp", "")}
            elif "city" in data:
                return {"city": data["city"], "isp": data.get("isp", "")}
        except (json.JSONDecodeError, TypeError):
            pass

        return None
    except Exception:
        return None


def _sense_location() -> Dict[str, Any]:
    """获取当前位置信息。

    策略：
    1. 环境变量 COGITO_WEATHER_CITY（手动覆盖）
    2. IP 归属查询（轮询多个国内服务，利用直连规则绕过代理）
    3. 系统时区推断（永远兜底）

    策略 2 利用了代理软件的普遍行为：GEOIP CN DIRECT。
    国内域名走直连，拿到的必定是真实宽带出口 IP。
    不管用户开没开代理，这条链都不会被污染。

    Returns:
        {"city": "...", "timezone": "...", "source": "env"|"ipip"|"tb"|"tz"}
    """
    sys_tz = str(datetime.now().astimezone().tzinfo)

    # ── 策略 1: 环境变量手动覆盖 ──
    city_override = os.environ.get("COGITO_WEATHER_CITY", "").strip()
    if city_override:
        return {
            "city": city_override,
            "timezone": sys_tz,
            "source": "env",
        }

    # ── 策略 2: IP 归属查询（主策略，轮询多个国内服务）──
    for url in _IP_LOOKUP_SERVICES:
        result = _query_ip_location(url)
        if result and result["city"]:
            source = "ipip" if "ipip" in url else ("tb" if "taobao" in url else "ip")
            return {
                "city": result["city"],
                "timezone": sys_tz,
                "source": source,
            }

    # ── 策略 3: 系统时区推断（兜底）──
    tz_city_map = {
        "CST": "中国",
        "Asia/Shanghai": "上海",
        "Asia/Hong_Kong": "香港",
        "Asia/Tokyo": "东京",
        "Asia/Seoul": "首尔",
        "Asia/Singapore": "新加坡",
    }
    city = tz_city_map.get(sys_tz, f"({sys_tz})")
    return {
        "city": city,
        "timezone": sys_tz,
        "source": "tz",
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


# ── 天气传感器（wttr.in 免费接口）──

# 英文天气描述 → 中文映射（wttr.in 兜底用）
_WTTR_WEATHER_MAP = {
    "sunny": "晴", "clear": "晴",
    "partly cloudy": "多云", "cloudy": "多云", "overcast": "阴",
    "mist": "雾", "fog": "雾", "haze": "霾",
    "light rain": "小雨", "patchy light rain": "小雨",
    "light rain shower": "阵雨",
    "moderate rain": "中雨", "heavy rain": "大雨",
    "light drizzle": "毛毛雨",
    "thunder": "雷阵雨",
    "light snow": "小雪", "snow": "雪",
}

def _sense_weather(city: str = "") -> Dict[str, Any]:
    """获取天气信息。wttr.in 免费接口，无需 Key。

    Args:
        city: 城市名（空则自动从 _sense_location 获取）
    """
    result: Dict[str, Any] = {"available": False}

    # 如果没有指定城市，用 location 传感器自动获取
    if not city:
        try:
            city = _sense_location().get("city", "北京")
        except Exception:
            city = "北京"

    # 时区级的模糊定位（如"中国"）→ 天气查询用北京兜底
    _TZ_FALLBACK_CITIES = {"中国": "北京"}
    weather_city = _TZ_FALLBACK_CITIES.get(city, city)

    # ── wttr.in（免费，无需 Key，全球覆盖）──
    try:
        import urllib.request
        import urllib.parse
        import json

        city_encoded = urllib.parse.quote(weather_city)
        url = f"https://wttr.in/{city_encoded}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Cogito/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current_condition", [{}])[0]
        if current:
            # 英文天气描述 → 中文
            weather_en = current.get("weatherDesc", [{}])[0].get("value", "").lower()
            weather_cn = _WTTR_WEATHER_MAP.get(weather_en, weather_en)

            result["available"] = True
            result["city"] = weather_city
            result["weather"] = weather_cn
            result["temperature"] = current.get("temp_C", "")
            result["humidity"] = current.get("humidity", "")
            result["wind_direction"] = current.get("winddir16Point", "")
            result["wind_power"] = current.get("windspeedKmph", "")
            result["source"] = "wttr.in"
    except ImportError:
        logger.debug("urllib 不可用，无法查询天气")
    except Exception as exc:
        logger.debug("wttr.in 天气查询失败: %s", exc)

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

    # 位置（在时间后立即显示，供 LLM 感知）
    try:
        loc_data = _sense_location()
        parts.append(f"📍 {loc_data['city']}")
    except Exception:
        pass

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


def get_location() -> Dict[str, Any]:
    """获取当前位置信息（独立于 snapshot）。

    供 engine.py 等模块直接调用，返回结构化数据。
    """
    return _sense_location()


def get_weather() -> Dict[str, Any]:
    """获取当前位置天气（独立于 snapshot）。

    城市自动从 _sense_location() 获取，也可通过 COGITO_WEATHER_CITY 覆盖。
    """
    city = os.environ.get("COGITO_WEATHER_CITY", "")
    return _sense_weather(city=city)
