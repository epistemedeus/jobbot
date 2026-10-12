"""How much of the catalog JobBot can work, and where this candidate is actually present.

Two different numerators share one denominator, and the denominator is always the
catalog in scope — never "all the portals in the country", which nobody can count:

* **reach** is about the tool. A channel is `proven` when a capability was assessed
  supported on it, `wired` when an adapter is registered for its platform but nothing
  was proven yet, and `pending` otherwise. Belonging to a known ATS proves nothing.
* **presence** is about the person, and it only ever counts *evidence*. A channel with
  no local receipt is not reported as absent: it is a channel we cannot vouch for.

The pending side is a roadmap, not a lament: an ATS family with no adapter carries the
number of channels and employers that implementing it would unlock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from jobbot.catalog.models import Capability, CapabilityStatus, Channel
from jobbot.catalog.registry import SourceCatalog
from jobbot.companies.urls import canonical_key, semantic_key

UNKNOWN_GROUP = "unknown"


class ReachState(StrEnum):
    """What JobBot can do with a channel today."""

    PROVEN = "proven"
    """A capability was assessed supported here, with a date and a reason."""
    WIRED = "wired"
    """An adapter serves this platform, but nothing was proven on this channel."""
    PENDING = "pending"
    """No adapter. Implementing its platform is what would unlock it."""


class AdapterLookup(Protocol):
    def supports(self, key: str | None) -> bool: ...


@dataclass(frozen=True)
class CoverageGroup:
    """One slice of the catalog (an ATS family, a sector) with both numerators."""

    label: str
    channels: int
    employers: int
    proven: int
    wired: int
    present: int

    @property
    def reachable(self) -> int:
        return self.proven + self.wired

    @property
    def pending(self) -> int:
        return self.channels - self.reachable

    @property
    def reach_pct(self) -> float:
        return _pct(self.reachable, self.channels)

    @property
    def presence_pct(self) -> float:
        return _pct(self.present, self.channels)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "channels": self.channels,
            "employers": self.employers,
            "proven": self.proven,
            "wired": self.wired,
            "pending": self.pending,
            "present": self.present,
            "reach_pct": self.reach_pct,
            "presence_pct": self.presence_pct,
        }


@dataclass(frozen=True)
class CoverageReport:
    """The indicator: one denominator, two numerators, and what to build next."""

    country: str
    catalog_version: str
    capability: Capability
    total: CoverageGroup
    by_ats: tuple[CoverageGroup, ...] = ()
    by_sector: tuple[CoverageGroup, ...] = ()

    @property
    def unlocks(self) -> tuple[CoverageGroup, ...]:
        """Platforms with nothing wired, biggest first: implementing one unlocks these."""
        return tuple(
            group
            for group in self.by_ats
            if group.reachable == 0 and group.label != UNKNOWN_GROUP
        )

    @property
    def unidentified(self) -> CoverageGroup | None:
        """Channels whose platform nobody has named yet: recon, not implementation."""
        return next((g for g in self.by_ats if g.label == UNKNOWN_GROUP), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "country": self.country or None,
            "catalog_version": self.catalog_version,
            "capability": self.capability.value,
            "total": self.total.to_dict(),
            "by_ats": [group.to_dict() for group in self.by_ats],
            "by_sector": [group.to_dict() for group in self.by_sector],
            "unlocks": [group.to_dict() for group in self.unlocks],
            "unidentified": self.unidentified.to_dict() if self.unidentified else None,
        }


def reach_state(
    channel: Channel,
    *,
    adapters: AdapterLookup | None = None,
    capability: Capability = Capability.JOB_LISTING,
) -> ReachState:
    if channel.capability(capability).status is CapabilityStatus.SUPPORTED:
        return ReachState.PROVEN
    if adapters is not None and adapters.supports(channel.platform.adapter_key):
        return ReachState.WIRED
    return ReachState.PENDING


def presence_keys(channel: Channel) -> tuple[str, ...]:
    """The keys a local receipt may have been written under for this channel."""
    keys = {semantic_key(channel.canonical_url), canonical_key(channel.canonical_url)}
    if channel.entry_url != channel.canonical_url:
        keys.add(canonical_key(channel.entry_url))
    return tuple(sorted(keys))


def measure_coverage(
    catalog: SourceCatalog,
    *,
    country: str = "",
    adapters: AdapterLookup | None = None,
    presence: Mapping[str, Any] | None = None,
    capability: Capability = Capability.JOB_LISTING,
) -> CoverageReport:
    """Count the catalog in scope. Reads nothing, opens nothing, writes nothing."""
    wanted = (country or "").strip().casefold()
    channels = [
        channel
        for channel in catalog.channels
        if not wanted or (channel.country or "").casefold() == wanted
    ]
    evidence = presence or {}

    ats_rows: dict[str, list[Channel]] = {}
    sector_rows: dict[str, list[Channel]] = {}
    employers_total: set[str] = set()
    ats_employers: dict[str, set[str]] = {}
    sector_employers: dict[str, set[str]] = {}

    for channel in channels:
        employers = catalog.employers_of(channel.channel_id)
        employer_ids = {e.employer_id for e in employers}
        employers_total |= employer_ids

        family = channel.platform.ats_family or UNKNOWN_GROUP
        ats_rows.setdefault(family, []).append(channel)
        ats_employers.setdefault(family, set()).update(employer_ids)

        for sector in {e.sector or UNKNOWN_GROUP for e in employers} or {UNKNOWN_GROUP}:
            sector_rows.setdefault(sector, []).append(channel)
            sector_employers.setdefault(sector, set()).update(employer_ids)

    def group(label: str, rows: list[Channel], employer_ids: set[str]) -> CoverageGroup:
        states = [reach_state(c, adapters=adapters, capability=capability) for c in rows]
        return CoverageGroup(
            label=label,
            channels=len(rows),
            employers=len(employer_ids),
            proven=states.count(ReachState.PROVEN),
            wired=states.count(ReachState.WIRED),
            present=sum(1 for c in rows if any(k in evidence for k in presence_keys(c))),
        )

    return CoverageReport(
        country=country,
        catalog_version=catalog.catalog_version,
        capability=capability,
        total=group("total", channels, employers_total),
        by_ats=_sorted(group(k, v, ats_employers[k]) for k, v in ats_rows.items()),
        by_sector=_sorted(group(k, v, sector_employers[k]) for k, v in sector_rows.items()),
    )


def _sorted(groups: Any) -> tuple[CoverageGroup, ...]:
    return tuple(sorted(groups, key=lambda g: (-g.channels, g.label)))


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(100.0 * part / whole, 1)
