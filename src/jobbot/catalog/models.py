"""Employer ↔ channel catalog model (public knowledge; never candidate data).

An employer may publish in several channels and a group channel may publish for several
subsidiaries, so the relation is many-to-many and lives in :class:`EmployerChannel`. The
ATS family is a vendor the page revealed, not the employer and not a capability: what
JobBot can do with a channel is stated one capability at a time in
:class:`CapabilityAssessment`, and starts `unknown`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from jobbot.companies.models import KnowledgeStatus, utc_now
from jobbot.companies.urls import semantic_key


class SourceType(StrEnum):
    """What the URL is, before anyone decides whether to read it."""

    LISTING = "listing"
    """A page that lists vacancies (the only type listing extraction may touch)."""
    ACCESS = "access"
    """Corporate "trabaja con nosotros" page: a door, not a list."""
    CV_INBOX = "cv_inbox"
    """General CV reception: no vacancy, a form that stores a résumé."""
    JOB_POSTING = "job_posting"
    """One vacancy kept as evidence that the employer hires through this host."""
    UNKNOWN = "unknown"


class ReadState(StrEnum):
    """Result of one reading. Never a verdict about the portal."""

    NOT_READ = "not_read"
    FETCHED = "fetched"
    JS_REQUIRED = "js_required"
    NO_CONTENT = "no_content"
    READER_ERROR = "reader_error"
    PENDING_DESTINATION = "pending_destination"


class ChannelRelation(StrEnum):
    """How an employer relates to a channel."""

    OWNER = "owner"
    GROUP = "group"
    """A holding's channel that also publishes for its subsidiaries."""
    INTERMEDIARY = "intermediary"
    """An agency or outsourcer: the employer of each vacancy is a client, not this brand."""


class Capability(StrEnum):
    DISCOVERY = "discovery"
    JOB_LISTING = "job_listing"
    JOB_DETAIL = "job_detail"
    APPLICATION_PREPARE = "application_prepare"
    APPLICATION_SUBMIT = "application_submit"


class CapabilityStatus(StrEnum):
    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


class CapabilityAssessment(BaseModel):
    """One capability, one verdict, with the date and the reason behind it."""

    capability: Capability
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    checked_at: datetime | None = None
    reason: str = ""


class PlatformBinding(BaseModel):
    """The platform currently serving a channel — configuration with evidence."""

    ats_family: str = "unknown"
    tenant: str | None = None
    site: str | None = None
    adapter_key: str | None = None
    """Set only when an adapter exists *and* was validated against this channel."""
    evidence_url: str | None = None
    observed_at: datetime | None = None


class ChannelHealth(BaseModel):
    """When it was researched, when it last answered, and what broke."""

    researched_at: datetime | None = None
    last_read_state: ReadState = ReadState.NOT_READ
    last_successful_fetch_at: datetime | None = None
    last_error: str | None = None
    redirect_from: str | None = None
    migrated_at: datetime | None = None
    replaced_by: str | None = None


class Channel(BaseModel):
    """One hiring surface: where it is, what served it, and what we may do with it."""

    channel_id: str = Field(min_length=1)
    entry_url: str = Field(min_length=1)
    """URL as it was handed to us, kept verbatim as evidence."""
    canonical_url: str = Field(min_length=1)
    """Entry URL minus identified tracking; tenant, country and search survive."""
    observed_url: str | None = None
    resolved_url: str | None = None
    linked_from: str | None = None
    """Corporate page that links this channel, when a page is what revealed it."""
    source_type: SourceType = SourceType.UNKNOWN
    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE
    enabled: bool = False
    country: str | None = None
    platform: PlatformBinding = Field(default_factory=PlatformBinding)
    health: ChannelHealth = Field(default_factory=ChannelHealth)
    capabilities: list[CapabilityAssessment] = Field(default_factory=list)
    notes: str | None = None

    @property
    def key(self) -> str:
        return semantic_key(self.canonical_url)

    def capability(self, capability: Capability) -> CapabilityAssessment:
        """Stored assessment, or `unknown`: a missing verdict is not a yes."""
        for assessment in self.capabilities:
            if assessment.capability == capability:
                return assessment
        return CapabilityAssessment(
            capability=capability,
            status=CapabilityStatus.UNKNOWN,
            reason="never probed",
        )

    def assess(
        self,
        capability: Capability,
        status: CapabilityStatus,
        *,
        reason: str = "",
        now: datetime | None = None,
    ) -> CapabilityAssessment:
        assessment = CapabilityAssessment(
            capability=capability,
            status=status,
            checked_at=now or utc_now(),
            reason=reason,
        )
        self.capabilities = [a for a in self.capabilities if a.capability != capability] + [
            assessment
        ]
        return assessment


class Employer(BaseModel):
    """An employer or brand. A group link is only ever written with evidence."""

    employer_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    sector: str | None = None
    country: str | None = None
    parent_group_id: str | None = None
    evidence_url: str | None = None


class EmployerChannel(BaseModel):
    """The many-to-many link, with the evidence that justifies it."""

    employer_id: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    relation: ChannelRelation = ChannelRelation.OWNER
    evidence_url: str | None = None
    verified_at: datetime | None = None
