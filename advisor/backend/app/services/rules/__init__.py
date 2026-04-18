"""Rule registry.

Each rule is a Python module under this package. The rule engine iterates
over ``RULES`` at the top of every cycle. Adding a new rule is a one-file
change plus one entry in this list.
"""
from app.services.rules.base import Rule
from app.services.rules.device_offline import DeviceOfflineRule
from app.services.rules.disk_high import DiskHighRule
from app.services.rules.ha_connection_health import (
    HaConnectionAuthFailureRule,
    HaConnectionUnexpectedPayloadRule,
    HaConnectionUnreachableRule,
)
from app.services.rules.ollama_unavailable import OllamaUnavailableRule
from app.services.rules.pi_cpu_high import PiCpuHighRule
from app.services.rules.service_down import ServiceDownRule
from app.services.rules.thread_border_router_offline import (
    ThreadBorderRouterOfflineRule,
)
from app.services.rules.unknown_device import UnknownDeviceRule
from app.services.rules.vpn_leak import VpnLeakRule

RULES: list[Rule] = [
    PiCpuHighRule(),
    DiskHighRule(),
    ServiceDownRule(),
    DeviceOfflineRule(),
    OllamaUnavailableRule(),
    UnknownDeviceRule(),
    VpnLeakRule(),
    HaConnectionAuthFailureRule(),
    HaConnectionUnreachableRule(),
    HaConnectionUnexpectedPayloadRule(),
    ThreadBorderRouterOfflineRule(),
]
