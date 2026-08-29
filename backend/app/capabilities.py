"""Capability registry.

Domain code only ever asks for a logical capability (`drive.list_files`,
`github.get_commits`, …). This module records which of them the configured
data provider can actually answer, so a feature that depends on a capability
nobody serves is disabled honestly instead of failing at call time.

Every capability here is a read. The Apps Script bridge exposes a fixed
read-only surface and the GitHub client only ever issues GETs, so there is no
write for an allowlist to reject.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("compass.capabilities")

CONNECTORS = [
    "google_calendar",
    "google_drive",
    "google_docs",
    "google_sheets",
    "google_slides",
    "gmail",
    "google_meet",
    "github",
    "canvas",
]

# logical capability -> the connector it belongs to.
_CAPABILITY_CONNECTORS: dict[str, str] = {
    "drive.list_files": "google_drive",
    "drive.search_files": "google_drive",
    "docs.get_text": "google_docs",
    "sheets.get_values": "google_sheets",
    "sheets.get_metadata": "google_sheets",
    "slides.get_presentation": "google_slides",
    "calendar.list_events": "google_calendar",
    # Lets Compass find the College OS calendars (🎓 Academic, ⭐ Opportunities,
    # …) instead of only reading `primary`.
    "calendar.list_calendars": "google_calendar",
    "gmail.list_messages": "gmail",
    "gmail.get_message": "gmail",
    "meet.list_conference_records": "google_meet",
    "meet.list_participants": "google_meet",
    "github.get_repositories": "github",
    "github.get_commits": "github",
    "github.get_pull_requests": "github",
    "github.get_checks": "github",
}
for _connector in CONNECTORS:
    _CAPABILITY_CONNECTORS[f"{_connector}.validate"] = _connector

# Capabilities a connector can be missing while still counting as fully
# supported — extras, not the reason the connector exists.
_OPTIONAL = {"drive.search_files", "sheets.get_metadata", "meet.list_participants",
             "calendar.list_calendars", "github.get_checks"}


@dataclass
class CapabilityRegistry:
    available: set[str] = field(default_factory=set)
    missing: list[str] = field(default_factory=list)
    checked_at: str | None = None

    def resolve(self, capability: str) -> str | None:
        """The capability itself when the provider serves it, else None."""
        return capability if capability in self.available else None

    def connector_status(self, connector: str) -> str:
        caps = [c for c, conn in _CAPABILITY_CONNECTORS.items() if conn == connector]
        if not any(c in self.available for c in caps):
            return "unsupported"
        core = [c for c in caps if not c.endswith(".validate") and c not in _OPTIONAL]
        return "supported" if all(c in self.available for c in core) else "degraded"

    def capabilities_for(self, connector: str) -> list[str]:
        return sorted(c for c, conn in _CAPABILITY_CONNECTORS.items()
                      if conn == connector and c in self.available)


def build_bridge_registry(supported: list[str], checked_at: str | None = None) -> CapabilityRegistry:
    """Registry for the Apps Script bridge + GitHub PAT.

    Neither provider has tool-name indirection to discover — both answer
    logical capability names directly — so the registry is just the set the
    provider serves. Anything it cannot serve (Google Meet, GitHub checks) is
    simply absent, and `connector_status` reports that honestly.
    """
    available = set(supported) & set(_CAPABILITY_CONNECTORS)
    return CapabilityRegistry(
        available=available,
        missing=sorted(c for c in _CAPABILITY_CONNECTORS if c not in available),
        checked_at=checked_at,
    )


_registry: CapabilityRegistry | None = None


async def discover_bridge_capabilities(force: bool = False) -> CapabilityRegistry:
    """Install the bridge registry. No network call — the surface is fixed."""
    global _registry
    from . import providers
    from .util import now_iso

    if _registry is not None and not force:
        return _registry
    _registry = build_bridge_registry(providers.bridge_capabilities(), checked_at=now_iso())
    if _registry.missing:
        logger.info("[capabilities] unavailable on this path: %s", ", ".join(_registry.missing))
    return _registry


def current_registry() -> CapabilityRegistry | None:
    return _registry


def set_registry(registry: CapabilityRegistry | None) -> None:
    global _registry
    _registry = registry
