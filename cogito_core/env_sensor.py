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
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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


# ── 位置传感器 ──

def _sense_location() -> Dict[str, Any]:
    """获取当前位置信息。

    优先级：
    1. 环境变量 COGITO_WEATHER_CITY（手动覆盖）
    2. 高德 IP 定位（需要 AMAP key，国内最准，不受代理影响）
    3. ip-api.com（免费，国际用户兜底，受代理影响）
    4. 系统时区推断（永远可用）

    Returns:
        {"city": "...", "timezone": "...", "source": "env"|"amap"|"ip"|"tz"}
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

    # ── 策略 2: 高德 IP 定位（国内用户首选，不受代理影响）──
    amap_key = os.environ.get("AMAP_MAPS_API_KEY", os.environ.get("AMAP_API_KEY", ""))
    if amap_key:
        try:
            import urllib.request
            url = f"https://restapi.amap.com/v3/ip?key={amap_key}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            province = data.get("province", "")
            city = data.get("city", "")
            if city:
                # 直辖市：province="北京市" city="" → 用 province
                location_name = city or province or ""
                if location_name:
                    return {
                        "city": location_name,
                        "timezone": sys_tz,
                        "source": "amap",
                    }
        except Exception:
            logger.debug("高德 IP 定位失败，降级")

    # ── 策略 3: ip-api.com（国际用户，受代理影响需冲突检测）──
    try:
        import urllib.request
        url = "http://ip-api.com/json/?fields=city,regionName,country,timezone"
        req = urllib.request.Request(url, headers={"User-Agent": "Cogito/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ip_city = data.get("city", "")
        ip_region = data.get("regionName", "")
        ip_country = data.get("country", "")
        ip_tz = data.get("timezone", "")

        # 时区冲突检测：系统时区是 CST（国内）但 IP 来自海外 → 代理干扰 → 跳过
        ip_looks_proxied = (
            ip_country and ip_country != "China" and
            sys_tz in ("CST", "Asia/Shanghai")
        )
        if not ip_looks_proxied and ip_city:
            # 中国城市直接用 city 名，海外附加国家（city==country 时省略重复）
            if ip_country == "China" and ip_city:
                location_name = ip_city
            elif ip_city == ip_country:
                location_name = ip_country
            elif ip_city and ip_country:
                location_name = f"{ip_city}, {ip_country}"
            elif ip_country:
                location_name = ip_country
            else:
                location_name = ""
            if location_name:
                return {
                    "city": location_name,
                    "timezone": ip_tz or sys_tz,
                    "source": "ip",
                }
        elif ip_looks_proxied:
            logger.debug("IP 来自海外但系统时区为国内 → 代理干扰，跳过 ip-api")
    except Exception:
        logger.debug("ip-api.com 定位失败，降级到时区推断")

    # ── 策略 4: 系统时区推断 ──
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


# ── 天气传感器（高德优先，wttr.in 兜底）──

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
    """获取天气信息。高德 API 优先，wttr.in 免费兜底。

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

    # ── 策略 1: 高德天气 API（需要 Key，国内最准）──
    api_key = os.environ.get("AMAP_MAPS_API_KEY", os.environ.get("AMAP_API_KEY", ""))
    if api_key:
        try:
            import urllib.request
            import urllib.parse
            import json

            # 英文城市名 → 中文映射（IP 定位可能返回英文名）
            _EN_TO_CN_CITY = {
                "Hong Kong": "香港", "Kowloon": "香港",
                "Beijing": "北京", "Shanghai": "上海",
                "Guangzhou": "广州", "Shenzhen": "深圳",
                "Hangzhou": "杭州", "Chengdu": "成都",
                "Tokyo": "东京", "Seoul": "首尔",
                "Singapore": "新加坡", "Bangkok": "曼谷",
                "London": "伦敦", "New York": "纽约",
                "Los Angeles": "洛杉矶", "San Francisco": "旧金山",
                "Taipei": "台北", "Macau": "澳门",
            }
            city_cn = _EN_TO_CN_CITY.get(weather_city, weather_city)
            city_encoded = urllib.parse.quote(city_cn)

            url = (
                f"https://restapi.amap.com/v3/weather/weatherInfo"
                f"?key={api_key}&city={city_encoded}&extensions=base"
            )
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") == "1" and data.get("lives"):
                live = data["lives"][0]
                if "weather" in live:
                    result["available"] = True
                    result["city"] = live.get("city", city_cn)
                    result["weather"] = live.get("weather", "")
                    result["temperature"] = live.get("temperature", "")
                    result["wind_direction"] = live.get("winddirection", "")
                    result["wind_power"] = live.get("windpower", "")
                    result["humidity"] = live.get("humidity", "")
                    result["report_time"] = live.get("reporttime", "")
                    result["source"] = "amap"
                    return result
        except Exception as exc:
            logger.debug("高德天气查询失败: %s", exc)

    # ── 策略 2: wttr.in（免费，无需 Key，全球覆盖）──
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

    需要 AMAP_MAPS_API_KEY 或 AMAP_API_KEY 环境变量。
    城市自动从 _sense_location() 获取，也可通过 COGITO_WEATHER_CITY 覆盖。
    """
    city = os.environ.get("COGITO_WEATHER_CITY", "")
    return _sense_weather(city=city)
