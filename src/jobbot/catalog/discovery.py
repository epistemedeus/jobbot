"""Discovery over the catalog: contracts, outcomes and the service that joins them.

The service depends on three interfaces — where the channels come from, whether we may
read one, and which adapter serves it — so a test injects an in-memory repository, a fake
registry and fixtures instead of the network, and a new portal is a new factory rather
than a change here.

Nothing silently becomes "no vacancies": a channel with no adapter, one we may not read,
one whose page could not be extracted and a search that honestly returned zero are four
different outcomes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from jobbot.catalog.models import Capability, CapabilityStatus, Channel, SourceType
from jobbot.jobs.sources import JobSearchQuery, JobSourceAdapter
from jobbot.models.job import JobPosting


class UnsupportedSourceError(LookupError):
    """No adapter is registered (and validated) for this channel."""


class OutcomeKind(StrEnum):
    READY = "ready"
    """Planning only: policy allows it and an adapter resolves."""
    FOUND = "found"
    EMPTY = "empty"
    """The source answered and had no vacancy. Only a real answer earns this."""
    DISABLED = "disabled"
    NOT_EXTRACTED = "not_extracted"
    """The page is not a listing, or its content never came back."""
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    CLOSED = "closed"
    UNSUPPORTED_SOURCE = "unsupported_source"
    ERROR = "error"


@dataclass(frozen=True)
class AccessDecision:
    """May we read this channel for this capability? `allowed=None` means nobody knows."""

    allowed: bool | None
    reason: str
    evidence: str = ""

    @classmethod
    def allow(cls, reason: str, *, evidence: str = "") -> AccessDecision:
        return cls(allowed=True, reason=reason, evidence=evidence)

    @classmethod
    def block(cls, reason: str, *, evidence: str = "") -> AccessDecision:
        return cls(allowed=False, reason=reason, evidence=evidence)

    @classmethod
    def unknown(cls, reason: str, *, evidence: str = "") -> AccessDecision:
        return cls(allowed=None, reason=reason, evidence=evidence)

    @property
    def is_blocked(self) -> bool:
        return self.allowed is False

    @property
    def is_unknown(self) -> bool:
        return self.allowed is None


class ChannelRepository(Protocol):
    def list_candidates(self, country: str) -> list[Channel]: ...


class AccessPolicy(Protocol):
    def assess(self, channel: Channel, capability: Capability) -> AccessDecision: ...


class SourceRegistry(Protocol):
    def resolve(self, channel: Channel) -> JobSourceAdapter: ...


@dataclass(frozen=True)
class ChannelOutcome:
    channel_id: str
    url: str
    kind: OutcomeKind
    reason: str
    jobs: tuple[JobPosting, ...] = ()


@dataclass(frozen=True)
class DiscoveryReport:
    country: str
    outcomes: tuple[ChannelOutcome, ...] = ()

    @property
    def jobs(self) -> tuple[JobPosting, ...]:
        return tuple(job for outcome in self.outcomes for job in outcome.jobs)

    def of_kind(self, *kinds: OutcomeKind) -> tuple[ChannelOutcome, ...]:
        wanted = set(kinds)
        return tuple(outcome for outcome in self.outcomes if outcome.kind in wanted)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for outcome in self.outcomes:
            out[outcome.kind.value] = out.get(outcome.kind.value, 0) + 1
        return out

    @property
    def needs_review(self) -> tuple[ChannelOutcome, ...]:
        return self.of_kind(
            OutcomeKind.NEEDS_REVIEW,
            OutcomeKind.BLOCKED,
            OutcomeKind.UNSUPPORTED_SOURCE,
            OutcomeKind.NOT_EXTRACTED,
            OutcomeKind.DISABLED,
            OutcomeKind.CLOSED,
            OutcomeKind.ERROR,
        )


class DiscoveryService:
    """Walks catalog channels through policy and registry. Owns no transport, no registry."""

    def __init__(
        self,
        channels: ChannelRepository,
        sources: SourceRegistry,
        policy: AccessPolicy,
    ) -> None:
        self.channels = channels
        self.sources = sources
        self.policy = policy

    def plan(self, *, country: str, capability: Capability = Capability.JOB_LISTING) -> (
        DiscoveryReport
    ):
        """Dry run: what could be explored, what needs review and why. Reads nothing."""
        outcomes = [
            self._gate(channel, capability) or self._ready(channel)
            for channel in self.channels.list_candidates(country)
        ]
        return DiscoveryReport(country=country, outcomes=tuple(outcomes))

    def discover(
        self,
        query: JobSearchQuery,
        *,
        country: str,
        capability: Capability = Capability.JOB_LISTING,
    ) -> DiscoveryReport:
        outcomes: list[ChannelOutcome] = []
        for channel in self.channels.list_candidates(country):
            blocked = self._gate(channel, capability)
            if blocked is not None:
                outcomes.append(blocked)
                continue
            outcomes.append(self._search(channel, query))
        return DiscoveryReport(country=country, outcomes=tuple(outcomes))

    # ── one channel ──────────────────────────────────────────────────────────

    def _gate(self, channel: Channel, capability: Capability) -> ChannelOutcome | None:
        """Everything that stops a channel before any reading. None means go ahead."""
        if channel.health.replaced_by:
            return self._outcome(
                channel,
                OutcomeKind.CLOSED,
                f"replaced by {channel.health.replaced_by}",
            )
        if channel.source_type is not SourceType.LISTING:
            return self._outcome(
                channel,
                OutcomeKind.NOT_EXTRACTED,
                f"source type {channel.source_type.value}: not a vacancy listing",
            )
        if not channel.enabled:
            return self._outcome(
                channel,
                OutcomeKind.DISABLED,
                "channel is a catalog candidate; enabling needs a supported capability",
            )
        decision = self.policy.assess(channel, capability)
        if decision.is_blocked:
            return self._outcome(channel, OutcomeKind.BLOCKED, decision.reason)
        if decision.is_unknown:
            return self._outcome(channel, OutcomeKind.NEEDS_REVIEW, decision.reason)
        try:
            self.sources.resolve(channel)
        except UnsupportedSourceError as exc:
            return self._outcome(channel, OutcomeKind.UNSUPPORTED_SOURCE, str(exc))
        return None

    def _ready(self, channel: Channel) -> ChannelOutcome:
        adapter_key = channel.platform.adapter_key or channel.platform.ats_family
        return self._outcome(channel, OutcomeKind.READY, f"adapter {adapter_key}")

    def _search(self, channel: Channel, query: JobSearchQuery) -> ChannelOutcome:
        try:
            adapter = self.sources.resolve(channel)
            jobs = adapter.search_jobs(query)
        except UnsupportedSourceError as exc:
            return self._outcome(channel, OutcomeKind.UNSUPPORTED_SOURCE, str(exc))
        except Exception as exc:  # noqa: BLE001 — one broken source never cancels the rest
            return self._outcome(channel, OutcomeKind.ERROR, f"{type(exc).__name__}: {exc}")
        if not jobs:
            return self._outcome(channel, OutcomeKind.EMPTY, "source answered with no vacancy")
        return self._outcome(
            channel,
            OutcomeKind.FOUND,
            f"{len(jobs)} vacancies",
            jobs=tuple(jobs),
        )

    @staticmethod
    def _outcome(
        channel: Channel,
        kind: OutcomeKind,
        reason: str,
        *,
        jobs: tuple[JobPosting, ...] = (),
    ) -> ChannelOutcome:
        return ChannelOutcome(
            channel_id=channel.channel_id,
            url=channel.canonical_url,
            kind=kind,
            reason=reason,
            jobs=jobs,
        )


# ── default implementations (still injected, never imported by the domain) ────


class CatalogChannelRepository:
    """Channels from a loaded catalog. A country is a stored fact, never the host's TLD."""

    def __init__(self, catalog_channels: Sequence[Channel]) -> None:
        self._channels = list(catalog_channels)

    def list_candidates(self, country: str) -> list[Channel]:
        wanted = (country or "").strip().casefold()
        if not wanted:
            return list(self._channels)
        return [c for c in self._channels if (c.country or "").casefold() == wanted]


class CapabilityAccessPolicy:
    """Reads the channel's own recorded verdicts. No record means unknown, not yes."""

    def assess(self, channel: Channel, capability: Capability) -> AccessDecision:
        assessment = channel.capability(capability)
        reason = assessment.reason or "never probed"
        if assessment.status is CapabilityStatus.SUPPORTED:
            return AccessDecision.allow(reason, evidence=channel.canonical_url)
        if assessment.status is CapabilityStatus.BLOCKED:
            return AccessDecision.block(f"blocked: {reason}", evidence=channel.canonical_url)
        if assessment.status is CapabilityStatus.UNSUPPORTED:
            return AccessDecision.block(f"unsupported: {reason}", evidence=channel.canonical_url)
        return AccessDecision.unknown(f"{capability.value} unknown: {reason}")


AdapterFactory = Callable[[Channel], JobSourceAdapter]


class AdapterKeyRegistry:
    """Explicit factories by adapter key. Data never names code that gets loaded."""

    def __init__(self, factories: Mapping[str, AdapterFactory]) -> None:
        self._factories = dict(factories)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def supports(self, key: str | None) -> bool:
        return bool(key) and key in self._factories

    def resolve(self, channel: Channel) -> JobSourceAdapter:
        key = channel.platform.adapter_key
        if not key:
            msg = (
                f"{channel.channel_id}: no adapter validated for "
                f"ats '{channel.platform.ats_family}'"
            )
            raise UnsupportedSourceError(msg)
        factory = self._factories.get(key)
        if factory is None:
            msg = f"{channel.channel_id}: unknown adapter key '{key}'"
            raise UnsupportedSourceError(msg)
        return factory(channel)
