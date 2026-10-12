"""The catalog itself: lookups, writes under evidence, persistence and review diff."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from jobbot.catalog.models import (
    Capability,
    CapabilityStatus,
    Channel,
    ChannelRelation,
    Employer,
    EmployerChannel,
)
from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.urls import semantic_key, slugify

CATALOG_VERSION = "0.1.0"
DEFAULT_CATALOG_FILE = "source_catalog.yaml"


class ChannelNotEnabled(ValueError):
    """Raised when something asks to enable a channel nothing has proven readable."""


class SourceCatalog(BaseModel):
    catalog_version: str = CATALOG_VERSION
    employers: list[Employer] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)
    links: list[EmployerChannel] = Field(default_factory=list)

    # ── lookups ──────────────────────────────────────────────────────────────

    def employer(self, employer_id: str) -> Employer | None:
        return next((e for e in self.employers if e.employer_id == employer_id), None)

    def find_employer(self, name: str) -> Employer | None:
        needle = slugify(name)
        for employer in self.employers:
            names = [employer.name, *employer.aliases]
            if employer.employer_id == needle or any(slugify(n) == needle for n in names):
                return employer
        return None

    def channel(self, channel_id: str) -> Channel | None:
        return next((c for c in self.channels if c.channel_id == channel_id), None)

    def find_channel(self, url: str) -> Channel | None:
        key = semantic_key(url)
        return next((c for c in self.channels if c.key == key), None)

    def channels_of(self, employer_id: str) -> list[Channel]:
        ids = {link.channel_id for link in self.links if link.employer_id == employer_id}
        return [c for c in self.channels if c.channel_id in ids]

    def employers_of(self, channel_id: str) -> list[Employer]:
        ids = [link.employer_id for link in self.links if link.channel_id == channel_id]
        return [e for e in self.employers if e.employer_id in ids]

    def link_for(self, employer_id: str, channel_id: str) -> EmployerChannel | None:
        return next(
            (
                link
                for link in self.links
                if link.employer_id == employer_id and link.channel_id == channel_id
            ),
            None,
        )

    # ── writes ───────────────────────────────────────────────────────────────

    def add_employer(self, employer: Employer) -> tuple[Employer, bool]:
        existing = self.employer(employer.employer_id) or self.find_employer(employer.name)
        if existing is not None:
            return existing, False
        self.employers.append(employer)
        return employer, True

    def add_channel(self, channel: Channel) -> tuple[Channel, bool]:
        """Add, or return the one already holding this canonical URL (never duplicate)."""
        existing = self.channel(channel.channel_id) or self.find_channel(channel.canonical_url)
        if existing is not None:
            return existing, False
        self.channels.append(channel)
        return channel, True

    def link(
        self,
        *,
        employer_id: str,
        channel_id: str,
        relation: ChannelRelation = ChannelRelation.OWNER,
        evidence_url: str | None = None,
        verified_at: datetime | None = None,
    ) -> tuple[EmployerChannel, bool]:
        existing = self.link_for(employer_id, channel_id)
        if existing is not None:
            return existing, False
        link = EmployerChannel(
            employer_id=employer_id,
            channel_id=channel_id,
            relation=relation,
            evidence_url=evidence_url,
            verified_at=verified_at,
        )
        self.links.append(link)
        return link, True

    def enable(
        self,
        channel_id: str,
        *,
        capability: Capability = Capability.JOB_LISTING,
    ) -> Channel:
        """
        Turn a channel on. Being in the catalog, or on a known ATS, is not a reason.

        The only reason is a capability somebody checked and recorded as supported.
        """
        channel = self.channel(channel_id)
        if channel is None:
            msg = f"unknown channel: {channel_id}"
            raise ChannelNotEnabled(msg)
        assessment = channel.capability(capability)
        if assessment.status != CapabilityStatus.SUPPORTED:
            msg = (
                f"{channel_id}: {capability.value} is {assessment.status.value}"
                f" ({assessment.reason or 'no check recorded'}); not enabled"
            )
            raise ChannelNotEnabled(msg)
        channel.enabled = True
        channel.status = KnowledgeStatus.ACTIVE
        return channel


# ── identifiers ──────────────────────────────────────────────────────────────


def channel_id_for(url: str, *, taken: Iterable[str] = ()) -> str:
    """Readable, deterministic id from the canonical URL; a clash gets a digest tail."""
    key = semantic_key(url)
    base = slugify(key)[:52].strip("-") or "channel"
    used = set(taken)
    if base not in used:
        return base
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{base}-{digest}"


def employer_id_for(name: str, *, taken: Iterable[str] = ()) -> str:
    base = slugify(name) or "employer"
    used = set(taken)
    if base not in used:
        return base
    digest = hashlib.sha1(name.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{base}-{digest}"


# ── review diff ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CatalogDiff:
    """What an import would change, so a human reviews a diff instead of a file."""

    added_employers: tuple[str, ...] = ()
    added_channels: tuple[str, ...] = ()
    changed_channels: tuple[tuple[str, str], ...] = ()
    added_links: tuple[tuple[str, str], ...] = ()
    removed_employers: tuple[str, ...] = field(default=())
    removed_channels: tuple[str, ...] = field(default=())

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.added_employers,
                self.added_channels,
                self.changed_channels,
                self.added_links,
                self.removed_employers,
                self.removed_channels,
            )
        )


def diff_catalogs(before: SourceCatalog, after: SourceCatalog) -> CatalogDiff:
    before_channels = {c.channel_id: c for c in before.channels}
    after_channels = {c.channel_id: c for c in after.channels}
    before_links = {(link.employer_id, link.channel_id) for link in before.links}
    after_links = {(link.employer_id, link.channel_id) for link in after.links}
    before_employers = {e.employer_id for e in before.employers}
    after_employers = {e.employer_id for e in after.employers}

    changed: list[tuple[str, str]] = []
    for channel_id, channel in after_channels.items():
        previous = before_channels.get(channel_id)
        if previous is None:
            continue
        for label in _channel_changes(previous, channel):
            changed.append((channel_id, label))

    return CatalogDiff(
        added_employers=tuple(sorted(after_employers - before_employers)),
        added_channels=tuple(sorted(set(after_channels) - set(before_channels))),
        changed_channels=tuple(changed),
        added_links=tuple(sorted(after_links - before_links)),
        removed_employers=tuple(sorted(before_employers - after_employers)),
        removed_channels=tuple(sorted(set(before_channels) - set(after_channels))),
    )


def _channel_changes(before: Channel, after: Channel) -> list[str]:
    labels: list[str] = []
    if before.canonical_url != after.canonical_url:
        labels.append(f"url: {before.canonical_url} → {after.canonical_url}")
    if before.source_type != after.source_type:
        labels.append(f"type: {before.source_type.value} → {after.source_type.value}")
    if before.platform.ats_family != after.platform.ats_family:
        labels.append(f"ats: {before.platform.ats_family} → {after.platform.ats_family}")
    if before.health.last_read_state != after.health.last_read_state:
        labels.append(
            f"read: {before.health.last_read_state.value} → {after.health.last_read_state.value}"
        )
    if before.enabled != after.enabled:
        labels.append(f"enabled: {before.enabled} → {after.enabled}")
    return labels


# ── persistence ──────────────────────────────────────────────────────────────


def default_catalog_path(root: Path | None = None) -> Path:
    from jobbot.config import load_config

    return load_config(root=root).catalog_path if root else load_config().catalog_path


def load_catalog(path: Path) -> SourceCatalog:
    if not path.is_file():
        return SourceCatalog()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SourceCatalog.model_validate(raw)


def save_catalog(catalog: SourceCatalog, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = catalog.model_dump(mode="json", exclude_none=False)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
