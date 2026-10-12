"""Import a researched inventory of hiring channels into the catalog, losing nothing.

The import is pure: it reads a seed document and returns a new catalog plus a report of
what it did and what it refused. Every channel arrives disabled, the counts the research
declared are checked against the counts we read, and a URL that cannot be a portal (a
documentation domain, a route with no host) is reported as rejected — never dropped in
silence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from jobbot.catalog.models import (
    Channel,
    ChannelHealth,
    ChannelRelation,
    Employer,
    PlatformBinding,
    ReadState,
    SourceType,
)
from jobbot.catalog.registry import (
    CatalogDiff,
    SourceCatalog,
    channel_id_for,
    diff_catalogs,
    employer_id_for,
)
from jobbot.companies.urls import (
    PrivateRouteRejected,
    ensure_not_reserved,
    semantic_url,
)


class SeedChannel(BaseModel):
    """One researched row: an employer seen publishing at a URL on a given day."""

    employer: str = Field(min_length=1)
    url: str = Field(min_length=1)
    sector: str | None = None
    source: str | None = None
    type: SourceType = SourceType.UNKNOWN
    ats: str = "unknown"
    read: ReadState = ReadState.NOT_READ
    relation: ChannelRelation = ChannelRelation.OWNER
    tenant: str | None = None
    site: str | None = None
    notes: str | None = None
    enabled: bool = False


class SeedExpectations(BaseModel):
    """What the research says it found. The importer must reproduce it."""

    employers: int | None = None
    channels: int | None = None
    sectors: int | None = None
    by_type: dict[str, int] = Field(default_factory=dict)
    by_read: dict[str, int] = Field(default_factory=dict)


class SeedDocument(BaseModel):
    catalog_version: str = "0.1.0"
    country: str | None = None
    researched_at: date | None = None
    notes: str | None = None
    expected: SeedExpectations = Field(default_factory=SeedExpectations)
    channels: list[SeedChannel] = Field(default_factory=list)
    research_queue: dict[str, list[str]] = Field(default_factory=dict)


class IssueLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ImportIssue:
    level: IssueLevel
    subject: str
    reason: str


@dataclass(frozen=True)
class ImportReport:
    """Everything the import saw: counts, refusals, shared channels and the review diff."""

    employers: int = 0
    channels: int = 0
    sectors: int = 0
    by_type: Mapping[str, int] = field(default_factory=dict)
    by_read: Mapping[str, int] = field(default_factory=dict)
    expected: SeedExpectations = field(default_factory=SeedExpectations)
    issues: tuple[ImportIssue, ...] = ()
    duplicates: tuple[tuple[str, str], ...] = ()
    shared_channels: tuple[tuple[str, tuple[str, ...]], ...] = ()
    research_queue: int = 0
    diff: CatalogDiff = field(default_factory=CatalogDiff)
    researched_at: date | None = None
    country: str | None = None

    @property
    def errors(self) -> tuple[ImportIssue, ...]:
        return tuple(i for i in self.issues if i.level is IssueLevel.ERROR)

    @property
    def mismatches(self) -> tuple[str, ...]:
        """Where the declared counts and the read counts disagree."""
        out: list[str] = []
        pairs: list[tuple[str, int | None, int]] = [
            ("employers", self.expected.employers, self.employers),
            ("channels", self.expected.channels, self.channels),
            ("sectors", self.expected.sectors, self.sectors),
        ]
        for label, declared, found in pairs:
            if declared is not None and declared != found:
                out.append(f"{label}: declared {declared}, imported {found}")
        for label, declared_map, found_map in (
            ("type", self.expected.by_type, self.by_type),
            ("read", self.expected.by_read, self.by_read),
        ):
            for key, declared_count in declared_map.items():
                found_count = found_map.get(key, 0)
                if declared_count != found_count:
                    out.append(f"{label} {key}: declared {declared_count}, imported {found_count}")
        return tuple(out)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.mismatches


def load_seed(path: Path) -> SeedDocument:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SeedDocument.model_validate(raw)


def import_seed(
    seed: SeedDocument,
    catalog: SourceCatalog | None = None,
    *,
    now: datetime | None = None,
) -> tuple[SourceCatalog, ImportReport]:
    """Merge a seed into a copy of the catalog. The input catalog is never mutated."""
    before = catalog.model_copy(deep=True) if catalog else SourceCatalog()
    working = before.model_copy(deep=True)
    moment = now or datetime.now(UTC)
    researched_at = (
        datetime.combine(seed.researched_at, datetime.min.time(), tzinfo=UTC)
        if seed.researched_at
        else None
    )

    issues: list[ImportIssue] = []
    duplicates: list[tuple[str, str]] = []
    by_type: dict[str, int] = {}
    by_read: dict[str, int] = {}
    sectors: set[str] = set()
    employers: set[str] = set()
    imported = 0

    for row in seed.channels:
        try:
            # Validate first (host, scheme, reserved names), then canonicalize from the
            # raw URL: `ensure_not_reserved` drops the query, where a tenant may live.
            ensure_not_reserved(row.url)
            canonical = semantic_url(row.url)
        except PrivateRouteRejected as exc:
            issues.append(ImportIssue(IssueLevel.ERROR, row.url, str(exc)))
            continue
        if row.enabled:
            issues.append(
                ImportIssue(
                    IssueLevel.ERROR,
                    row.url,
                    "seed asks for an enabled channel; imported disabled "
                    "(only a recorded supported capability enables one)",
                )
            )

        employer = _upsert_employer(working, row, country=seed.country)
        employers.add(employer.employer_id)
        if row.sector:
            sectors.add(row.sector)

        existing = working.find_channel(canonical)
        if existing is None:
            channel = _build_channel(
                row,
                canonical=canonical,
                country=seed.country,
                researched_at=researched_at,
                taken=[c.channel_id for c in working.channels],
            )
            working.add_channel(channel)
        else:
            channel = existing
            duplicates.append((canonical, channel.channel_id))
            _merge_channel(channel, row, researched_at=researched_at, issues=issues)

        working.link(
            employer_id=employer.employer_id,
            channel_id=channel.channel_id,
            relation=row.relation,
            evidence_url=row.source or canonical,
            verified_at=researched_at or moment,
        )
        imported += 1
        by_type[row.type.value] = by_type.get(row.type.value, 0) + 1
        by_read[row.read.value] = by_read.get(row.read.value, 0) + 1

    shared = tuple(
        (channel.channel_id, tuple(e.employer_id for e in working.employers_of(channel.channel_id)))
        for channel in working.channels
        if len(working.employers_of(channel.channel_id)) > 1
    )
    report = ImportReport(
        employers=len(employers),
        channels=imported,
        sectors=len(sectors),
        by_type=by_type,
        by_read=by_read,
        expected=seed.expected,
        issues=tuple(issues),
        duplicates=tuple(duplicates),
        shared_channels=shared,
        research_queue=sum(len(names) for names in seed.research_queue.values()),
        diff=diff_catalogs(before, working),
        researched_at=seed.researched_at,
        country=seed.country,
    )
    return working, report


def _upsert_employer(catalog: SourceCatalog, row: SeedChannel, *, country: str | None) -> Employer:
    existing = catalog.find_employer(row.employer)
    if existing is not None:
        if row.sector and not existing.sector:
            existing.sector = row.sector
        return existing
    employer = Employer(
        employer_id=employer_id_for(
            row.employer, taken=[e.employer_id for e in catalog.employers]
        ),
        name=row.employer,
        sector=row.sector,
        country=country,
    )
    catalog.add_employer(employer)
    return employer


def _build_channel(
    row: SeedChannel,
    *,
    canonical: str,
    country: str | None,
    researched_at: datetime | None,
    taken: list[str],
) -> Channel:
    return Channel(
        channel_id=channel_id_for(canonical, taken=taken),
        entry_url=row.url,
        canonical_url=canonical,
        observed_url=row.url,
        linked_from=row.source,
        source_type=row.type,
        enabled=False,
        country=country,
        platform=PlatformBinding(
            ats_family=row.ats or "unknown",
            tenant=row.tenant,
            site=row.site,
            adapter_key=None,
            evidence_url=row.source or canonical,
            observed_at=researched_at,
        ),
        health=_health(row, researched_at=researched_at),
        notes=row.notes,
    )


def _health(row: SeedChannel, *, researched_at: datetime | None) -> ChannelHealth:
    fetched = row.read is ReadState.FETCHED
    return ChannelHealth(
        researched_at=researched_at,
        last_read_state=row.read,
        last_successful_fetch_at=researched_at if fetched else None,
        last_error=None if row.read is not ReadState.READER_ERROR else "reader error on research",
        redirect_from=row.source,
    )


def _merge_channel(
    channel: Channel,
    row: SeedChannel,
    *,
    researched_at: datetime | None,
    issues: list[ImportIssue],
) -> None:
    """A second sighting adds what is missing and reports a contradiction; never overwrites."""
    observed = (row.ats or "unknown").strip()
    stored = channel.platform.ats_family
    if observed != "unknown" and stored == "unknown":
        channel.platform.ats_family = observed
        channel.platform.observed_at = researched_at
    elif observed != "unknown" and stored != observed:
        issues.append(
            ImportIssue(
                IssueLevel.WARNING,
                channel.channel_id,
                f"ats changed: stored {stored}, observed {observed}",
            )
        )
    if channel.source_type is SourceType.UNKNOWN and row.type is not SourceType.UNKNOWN:
        channel.source_type = row.type
    if row.read is not ReadState.NOT_READ:
        channel.health.last_read_state = row.read
        if row.read is ReadState.FETCHED and researched_at:
            channel.health.last_successful_fetch_at = researched_at
    if row.source and not channel.linked_from:
        channel.linked_from = row.source
