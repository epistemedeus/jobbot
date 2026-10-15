"""`jobs discover`: one command, one adapter per public source, a preview before storing.

Each source registers a factory here (Workday, UN Careers; Greenhouse … later).
An adapter turns one site into a `SiteOutcome`; this module decides, per posting, what
storing would do — so `--dry-run` and the real run print the same table. A site that
fails is reported and the others continue (#176).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.registry import CompanyRegistry
from jobbot.exit_codes import GENERIC_FAILURE, SUCCESS, UI_CHANGED
from jobbot.jobs.closing import ClosingState, closing_state
from jobbot.jobs.normalization import fold_text
from jobbot.jobs.repository import StoredJobIndex
from jobbot.models.job import JobPosting

_REMOTE_WORDS = frozenset({"remote", "remoto", "home based", "homebased"})


class SiteStatus(StrEnum):
    OK = "ok"
    EMPTY = "sin resultados"
    FAILED = "falló"
    ROBOTS = "bloqueado: robots"
    CHANGED = "forma cambiada"


@dataclass
class SiteOutcome:
    site: str
    status: SiteStatus
    jobs: list[JobPosting] = field(default_factory=list)
    detail: str = ""
    total: int | None = None
    feed_size: int | None = None
    """Items in the source's whole feed, when the source reads one feed and filters locally."""
    kept_ids: tuple[str, ...] = ()
    """Ids that passed the query and local filters, before ``--limit``."""

    @property
    def answered(self) -> bool:
        return self.status in {SiteStatus.OK, SiteStatus.EMPTY}


@dataclass(frozen=True)
class SiteTarget:
    url: str
    company: str | None = None


@dataclass(frozen=True)
class JobFilters:
    """``--location`` / ``--level``: local, accent- and case-insensitive, never a source query.

    ``location`` is a substring of the posting's place; "remote" (or "home-based") also
    keeps postings the source marked remote. ``levels`` are exact grades (``P-3``, ``CON``).
    """

    location: str | None = None
    levels: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return bool(self.location or self.levels)

    def keeps(self, job: JobPosting) -> bool:
        if self.location:
            needle = fold_text(self.location)
            place = fold_text(job.location or "")
            remote = needle in _REMOTE_WORDS and (job.remote_type or "").casefold() == "remote"
            if needle not in place and not remote:
                return False
        if self.levels:
            wanted = {fold_text(level) for level in self.levels}
            if fold_text(job.seniority or "") not in wanted:
                return False
        return True


class DiscoverAdapter(Protocol):
    name: str
    default_details: bool
    """Whether ``--details`` is on when the flag is not given (a read may have a cost)."""

    def site_target(self, raw: str) -> SiteTarget:
        """Validate one ``--site`` value; ``ValueError`` with a clear message if not this source."""
        ...

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]: ...

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
        filters: JobFilters | None = None,
    ) -> SiteOutcome: ...


_FACTORIES: dict[str, Callable[[], DiscoverAdapter]] = {}


def register_source(name: str, factory: Callable[[], DiscoverAdapter]) -> None:
    _FACTORIES[name] = factory


def source_names() -> list[str]:
    _load_builtin()
    return sorted(_FACTORIES)


def discover_adapter(name: str) -> DiscoverAdapter:
    _load_builtin()
    factory = _FACTORIES.get(name)
    if factory is None:
        known = ", ".join(sorted(_FACTORIES)) or "none"
        msg = f"Unknown --source {name!r} (known: {known})"
        raise ValueError(msg)
    return factory()


def _load_builtin() -> None:
    if "workday" not in _FACTORIES:
        from jobbot.adapters.workday.jobs import WorkdayDiscover

        register_source("workday", WorkdayDiscover)
    if "un-careers" not in _FACTORIES:
        from jobbot.adapters.un_careers.jobs import UnCareersDiscover

        register_source("un-careers", UnCareersDiscover)


def registry_sites_for(registry: CompanyRegistry, ats: str) -> list[SiteTarget]:
    """Career sites of one ATS that were not rejected, named after their company."""
    out: list[SiteTarget] = []
    for record in registry.companies:
        for site in record.career_sites:
            if str(site.ats) == ats and site.status != KnowledgeStatus.REJECTED:
                out.append(SiteTarget(url=site.url, company=record.name))
    return out


class Action(StrEnum):
    STORE = "guardar"
    UPDATE = "actualizar"
    SKIP = "omitir"


@dataclass(frozen=True)
class Decision:
    job: JobPosting
    action: Action
    reason: str = ""
    existing_id: str | None = None
    closing: ClosingState | None = None

    @property
    def stores(self) -> bool:
        return self.action is not Action.SKIP

    @property
    def label(self) -> str:
        bits = [self.action.value]
        if self.existing_id:
            bits.append(self.existing_id)
        if self.reason:
            bits.append(f"({self.reason})")
        if self.closing is ClosingState.SOON:
            bits.append("· cierra pronto")
        return " ".join(bits)


def unique_jobs(jobs: Sequence[JobPosting]) -> list[JobPosting]:
    """Several queries and sites can surface one vacancy; keep its first sighting."""
    seen: set[tuple[str, ...]] = set()
    out: list[JobPosting] = []
    for job in jobs:
        key = (job.source, job.source_job_id) if job.source_job_id else (job.url or job.title,)
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


def decide(
    jobs: Sequence[JobPosting],
    index: StoredJobIndex,
    *,
    now: datetime,
) -> list[Decision]:
    decisions: list[Decision] = []
    for job in unique_jobs(jobs):
        state = closing_state(job.closes_at, job.closes_on, now=now)
        existing = index.lookup(job)
        if state is ClosingState.EXPIRED:
            decisions.append(Decision(job, Action.SKIP, "cierre vencido", existing, state))
        elif job.ats_signals.get("can_apply") is False:
            decisions.append(Decision(job, Action.SKIP, "no admite postulación", existing, state))
        elif existing:
            decisions.append(Decision(job, Action.UPDATE, "", existing, state))
        else:
            decisions.append(Decision(job, Action.STORE, "", None, state))
    return decisions


def feed_summary(outcomes: Sequence[SiteOutcome]) -> tuple[int, int] | None:
    """``(N, M)``: items in the feed and distinct ones kept locally across every query.

    Only for sources that read one whole feed (``feed_size`` set); the size comes from
    the feed itself, never a constant.
    """
    read = [outcome for outcome in outcomes if outcome.feed_size is not None]
    if not read:
        return None
    size = max(outcome.feed_size or 0 for outcome in read)
    kept = {job_id for outcome in read for job_id in outcome.kept_ids}
    return size, len(kept)


def exit_code_for(outcomes: Sequence[SiteOutcome]) -> int:
    """0 if any site answered; 5 if the only site changed shape; else 1."""
    if any(outcome.answered for outcome in outcomes):
        return SUCCESS
    if len(outcomes) == 1 and outcomes[0].status is SiteStatus.CHANGED:
        return UI_CHANGED
    return GENERIC_FAILURE
