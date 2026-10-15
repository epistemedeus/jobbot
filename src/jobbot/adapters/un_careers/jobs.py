"""UN Careers as a job source: filter the public feed locally, map postings."""

from __future__ import annotations

from urllib.parse import urlparse

from jobbot.adapters.un_careers.feed import (
    FEED_URL,
    HOST,
    UnCareersClient,
    UnCareersError,
    UnCareersRobotsDisallowed,
    UnCareersShapeChanged,
    job_from_item,
    job_id_from_url,
    with_detail,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget
from jobbot.jobs.sources import JobSearchQuery
from jobbot.models.job import JobPosting


class UnCareersDiscover:
    """`jobs discover --source un-careers`: one feed, filtered here (it takes no query)."""

    name = "un-careers"
    default_details = False

    def __init__(self, client: UnCareersClient | None = None) -> None:
        self.client = client or UnCareersClient()

    def site_target(self, raw: str) -> SiteTarget:
        host = (urlparse(raw if "//" in raw else f"//{raw}").hostname or "").casefold()
        if host != HOST:
            msg = f"UN Careers reads one public feed ({FEED_URL}); --site is optional, got {raw!r}"
            raise ValueError(msg)
        return SiteTarget(url=FEED_URL)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        return [SiteTarget(url=FEED_URL)]

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
        filters: JobFilters | None = None,
    ) -> SiteOutcome:
        try:
            items = self.client.feed()
        except UnCareersRobotsDisallowed as exc:
            return SiteOutcome(HOST, SiteStatus.ROBOTS, detail=str(exc))
        except UnCareersShapeChanged as exc:
            return SiteOutcome(HOST, SiteStatus.CHANGED, detail=str(exc))
        except UnCareersError as exc:
            return SiteOutcome(HOST, SiteStatus.FAILED, detail=str(exc))
        matched = [job_from_item(item) for item in items if item.matches(query)]
        kept = [job for job in matched if filters is None or filters.keeps(job)]
        notes: list[str] = []
        jobs = [self._with_detail(job, notes) if details else job for job in kept[:limit]]
        detail = f"{len(jobs)} de {len(kept)} coincidencias; feed: {len(items)} avisos"
        if filters is not None and filters.active:
            detail += f"; {len(matched) - len(kept)} fuera de --location/--level"
        if notes:
            detail += "; " + "; ".join(notes)
        status = SiteStatus.OK if jobs else SiteStatus.EMPTY
        return SiteOutcome(
            HOST,
            status,
            jobs=jobs,
            detail=detail,
            total=len(kept),
            feed_size=len(items),
            kept_ids=tuple(job.source_job_id or job.url or job.title for job in kept),
        )

    def _with_detail(self, job: JobPosting, notes: list[str]) -> JobPosting:
        try:
            return with_detail(job, self.client.detail(job.source_job_id or ""))
        except UnCareersError as exc:
            notes.append(str(exc))
            return job


class UnCareersJobSource:
    """`JobSourceAdapter` view: search the feed, or read one posting by its URL."""

    def __init__(self, client: UnCareersClient | None = None) -> None:
        self.discover = UnCareersDiscover(client)

    def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        filters = JobFilters(location=query.location)
        outcome = self.discover.discover_site(
            SiteTarget(url=FEED_URL),
            query=query.query,
            limit=query.limit,
            details=False,
            filters=filters,
        )
        if not outcome.answered:
            raise UnCareersError(outcome.detail)
        return outcome.jobs

    def get_job(self, job_id: str) -> JobPosting:
        number = job_id_from_url(job_id)
        if number is None:
            msg = f"UnCareersJobSource.get_job needs a careers.un.org posting URL, got {job_id!r}"
            raise ValueError(msg)
        client = self.discover.client
        item = next((i for i in client.feed() if i.job_id == number), None)
        if item is None:
            msg = f"{job_id}: not in the UN Careers feed (closed or never published)"
            raise UnCareersError(msg)
        return with_detail(job_from_item(item), client.detail(number))
