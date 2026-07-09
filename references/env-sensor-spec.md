---
title: "Environment Sensor Specification"
description: "Specification for the EnvSensor module: capability probing protocol, environment data taxonomy, graceful degradation, and cross-platform adaptation."
tags: [cogito-engine, env-sensor, environment, specification]
---

# Environment Sensor Specification

## Purpose

EnvSensor gives the agent awareness of its runtime environment. Unlike the Temporal module (which provides time), EnvSensor discovers everything else the platform can reveal: weather, system information, foreground application, battery, network, and location. The module is optional and self-configuring — it probes what is available and reports only what it can access.

## Self-Discovery Protocol

On startup, the agent probes its environment for accessible data sources. The protocol is a simple capability check:

```
For each environment data category:
  1. Attempt to access the data source
  2. If access succeeds → mark category as "available"
  3. If access fails → mark category as "unavailable"
  4. If category is not applicable to this platform → omit entirely
```

The agent must NOT assume any specific API, command, or data source. It probes what its platform provides and adapts.

## Environment Data Categories

The following categories represent what an agent MIGHT discover. No category is mandatory. The agent reports only what it can actually access.

### System time

Always available (covered by Temporal module). EnvSensor does not duplicate time data.

### Weather

| Source examples | Probe method |
|----------------|-------------|
| OpenWeatherMap API, wttr.in, platform-native weather service | HTTP GET to weather endpoint; if platform has API key configured |

When weather is unavailable, the sensor omits the weather block.

### System information

| Data point | Probe examples by platform |
|-----------|--------------------------|
| CPU usage | `top` / `system_profiler` / `psutil` / `/proc/stat` |
| Memory usage | `vm_stat` / `free` / `psutil` / `/proc/meminfo` |
| Disk usage | `df` / `diskutil` / `psutil` |
| Uptime | `uptime` / `sysctl` / `/proc/uptime` |
| OS version | `sw_vers` / `uname` / `ver` |

The agent probes each data point independently. Partial system information is valid — report what you can get.

### Foreground application

| Platform | Probe method |
|----------|-------------|
| macOS | AppleScript `tell application "System Events"` or Accessibility API |
| Windows | `GetForegroundWindow` or `tasklist` |
| Linux | `xdotool getactivewindow getwindowname` or `swaymsg` |
| Headless/Docker | Not available — omit |

### Battery

| Platform | Probe method |
|----------|-------------|
| macOS | `pmset -g batt` or IOKit |
| Windows | `WMIC Path Win32_Battery` |
| Linux | `/sys/class/power_supply/BAT0/capacity` |

Desktop machines without batteries omit this category.

### Network status

| Data point | Probe method |
|-----------|-------------|
| Connection state | `ping` to known host / HTTP HEAD to public endpoint |
| SSID / network name | Platform-specific (macOS: `networksetup`, Linux: `iwgetid`) |
| IP address | `ifconfig` / `ip addr` / `hostname -I` |

### Geolocation

| Source | Probe method |
|--------|-------------|
| IP-based geolocation | HTTP GET to ip-api.com or similar |
| GPS / CoreLocation | Platform-native location API |

Location data requires user consent in most environments. The agent should probe availability but not automatically fetch location without permission.

## Graceful Degradation

When EnvSensor can access NO environment data beyond what Temporal already provides:

```xml
<env available="false" />
```

When EnvSensor discovers partial data:

```xml
<env available="true">
  <source time="system" system_info="shell" network="ping" />
</env>
```

The `<source>` element lists each category and the probe method that succeeded. This transparency lets downstream consumers know exactly what data is available and how it was obtained.

## Capability Probe Caching

The agent runs the full capability probe once at startup and caches the result. On subsequent turns, it reuses the cached capability map. If an environment data source becomes unavailable mid-session, the sensor reports the last known value with a `stale="true"` attribute.

## Output Format

When available:

```xml
<env available="true">
  <source time="system" weather="api" system_info="shell" foreground_app="ax" battery="iokit" network="ping" />
</env>
```

When only partial:

```xml
<env available="true">
  <source time="system" system_info="shell" />
</env>
```

When nothing beyond time:

```xml
<env available="false" />
```
