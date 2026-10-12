"""Discovery is wired by injection: no network, no concrete adapter, no silent zero."""

from __future__ import annotations

from jobbot.catalog.discovery import (
    AccessDecision,
    AdapterKeyRegistry,
    CapabilityAccessPolicy,
    CatalogChannelRepository,
    DiscoveryService,
    OutcomeKind,
    UnsupportedSourceError,
)
from jobbot.catalog.models import (
    Capability,
    CapabilityStatus,
    Channel,
    ChannelHealth,
    PlatformBinding,
    SourceType,
)
from jobbot.catalog.report import render_discovery_plan
from jobbot.jobs.sources import JobSearchQuery, JobSourceAdapter
from jobbot.models.job import JobPosting

QUERY = JobSearchQuery(query="cualquier oficio")


def _channel(
    channel_id: str = "demo",
    *,
    enabled: bool = True,
    source_type: SourceType = SourceType.LISTING,
    adapter_key: str | None = "demo_adapter",
    country: str | None = "CL",
    replaced_by: str | None = None,
) -> Channel:
    return Channel(
        channel_id=channel_id,
        entry_url=f"https://{channel_id}-demo.cl/empleos",
        canonical_url=f"https://{channel_id}-demo.cl/empleos",
        source_type=source_type,
        enabled=enabled,
        country=country,
        platform=PlatformBinding(ats_family="demo_ats", adapter_key=adapter_key),
        health=ChannelHealth(replaced_by=replaced_by),
    )


class FakeRepository:
    def __init__(self, *channels: Channel) -> None:
        self._channels = list(channels)

    def list_candidates(self, country: str) -> list[Channel]:
        return [c for c in self._channels if c.country == country]


class AllowAll:
    def assess(self, channel: Channel, capability: Capability) -> AccessDecision:
        del channel, capability
        return AccessDecision.allow("fixture policy")


class BlockAll:
    def assess(self, channel: Channel, capability: Capability) -> AccessDecision:
        del channel, capability
        return AccessDecision.block("robots.txt disallows this path")


class UnknownAccess:
    def assess(self, channel: Channel, capability: Capability) -> AccessDecision:
        del channel, capability
        return AccessDecision.unknown("terms not reviewed")


class StubSource:
    def __init__(
        self,
        jobs: list[JobPosting] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs = jobs or []
        self._error = error

    def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        del query
        if self._error is not None:
            raise self._error
        return list(self._jobs)

    def get_job(self, job_id: str) -> JobPosting:
        raise NotImplementedError(job_id)


class FakeRegistry:
    def __init__(self, adapter: JobSourceAdapter | None) -> None:
        self._adapter = adapter

    def resolve(self, channel: Channel) -> JobSourceAdapter:
        if self._adapter is None:
            msg = f"{channel.channel_id}: no adapter"
            raise UnsupportedSourceError(msg)
        return self._adapter


def _posting() -> JobPosting:
    return JobPosting(id="J0001", title="Cargo Demo", company="Empresa Demo")


def _service(adapter: JobSourceAdapter | None, policy: object = None, *channels: Channel) -> (
    DiscoveryService
):
    return DiscoveryService(
        channels=FakeRepository(*(channels or (_channel(),))),
        sources=FakeRegistry(adapter),
        policy=policy or AllowAll(),  # type: ignore[arg-type]
    )


def test_a_source_that_answers_with_vacancies_is_found() -> None:
    report = _service(StubSource([_posting()])).discover(QUERY, country="CL")

    assert report.counts == {OutcomeKind.FOUND.value: 1}
    assert [job.id for job in report.jobs] == ["J0001"]


def test_an_honest_zero_and_a_broken_source_are_different_results() -> None:
    """The bug this guards: a failure printed as "no vacancies here"."""
    empty = _service(StubSource([])).discover(QUERY, country="CL")
    broken = _service(StubSource(error=TimeoutError("read timeout"))).discover(QUERY, country="CL")

    assert empty.outcomes[0].kind is OutcomeKind.EMPTY
    assert broken.outcomes[0].kind is OutcomeKind.ERROR
    assert "TimeoutError" in broken.outcomes[0].reason
    assert broken.jobs == ()


def test_a_source_with_no_adapter_says_so() -> None:
    report = _service(None).discover(QUERY, country="CL")

    assert report.outcomes[0].kind is OutcomeKind.UNSUPPORTED_SOURCE


def test_access_decisions_separate_blocked_from_unknown() -> None:
    blocked = _service(StubSource([_posting()]), BlockAll()).discover(QUERY, country="CL")
    unknown = _service(StubSource([_posting()]), UnknownAccess()).discover(QUERY, country="CL")

    assert blocked.outcomes[0].kind is OutcomeKind.BLOCKED
    assert unknown.outcomes[0].kind is OutcomeKind.NEEDS_REVIEW
    assert blocked.jobs == () and unknown.jobs == ()


def test_a_candidate_channel_is_not_read() -> None:
    service = _service(StubSource([_posting()]), None, _channel(enabled=False))

    assert service.discover(QUERY, country="CL").outcomes[0].kind is OutcomeKind.DISABLED


def test_a_corporate_page_stays_out_of_listing_extraction() -> None:
    service = _service(StubSource([_posting()]), None, _channel(source_type=SourceType.ACCESS))
    outcome = service.discover(QUERY, country="CL").outcomes[0]

    assert outcome.kind is OutcomeKind.NOT_EXTRACTED
    assert "access" in outcome.reason


def test_a_replaced_channel_is_closed_not_empty() -> None:
    service = _service(
        StubSource([_posting()]),
        None,
        _channel(replaced_by="https://otro-demo.cl/empleos"),
    )

    assert service.discover(QUERY, country="CL").outcomes[0].kind is OutcomeKind.CLOSED


def test_the_adapter_can_be_swapped_without_touching_the_service() -> None:
    """Same DiscoveryService, two registries: one finds vacancies, the other has no adapter."""
    channel = _channel()
    with_adapter = DiscoveryService(
        channels=FakeRepository(channel),
        sources=FakeRegistry(StubSource([_posting()])),
        policy=AllowAll(),  # type: ignore[arg-type]
    )
    without = DiscoveryService(
        channels=FakeRepository(channel),
        sources=FakeRegistry(None),
        policy=AllowAll(),  # type: ignore[arg-type]
    )

    assert with_adapter.discover(QUERY, country="CL").outcomes[0].kind is OutcomeKind.FOUND
    assert without.discover(QUERY, country="CL").outcomes[0].kind is (
        OutcomeKind.UNSUPPORTED_SOURCE
    )


def test_the_plan_reads_nothing_and_still_explains_each_channel() -> None:
    def explode(query: JobSearchQuery) -> list[JobPosting]:
        raise AssertionError(f"plan must not search: {query}")

    adapter = StubSource([])
    adapter.search_jobs = explode  # type: ignore[method-assign]
    service = _service(
        adapter,
        None,
        _channel("uno"),
        _channel("dos", enabled=False),
        _channel("tres", source_type=SourceType.CV_INBOX),
    )

    report = service.plan(country="CL")

    assert report.counts == {
        OutcomeKind.READY.value: 1,
        OutcomeKind.DISABLED.value: 1,
        OutcomeKind.NOT_EXTRACTED.value: 1,
    }
    assert {o.channel_id for o in report.needs_review} == {"dos", "tres"}


def test_country_comes_from_the_catalog_not_from_the_host() -> None:
    repository = CatalogChannelRepository(
        [_channel("uno", country="CL"), _channel("dos", country=None)]
    )

    assert [c.channel_id for c in repository.list_candidates("cl")] == ["uno"]
    assert len(repository.list_candidates("")) == 2


def test_a_capability_nobody_checked_is_unknown_not_allowed() -> None:
    policy = CapabilityAccessPolicy()
    channel = _channel()

    assert policy.assess(channel, Capability.JOB_LISTING).is_unknown

    channel.assess(Capability.JOB_LISTING, CapabilityStatus.BLOCKED, reason="robots.txt")
    assert policy.assess(channel, Capability.JOB_LISTING).is_blocked

    channel.assess(Capability.JOB_LISTING, CapabilityStatus.SUPPORTED, reason="fixture read")
    assert policy.assess(channel, Capability.JOB_LISTING).allowed is True


def test_the_plan_groups_omitted_channels_by_reason_instead_of_one_line_each() -> None:
    """A seeded catalog omits hundreds of channels; the dry run stays readable."""
    service = _service(
        StubSource([_posting()]),
        None,
        *(_channel(f"c{index:03d}", enabled=False) for index in range(25)),
    )

    lines = render_discovery_plan(service.plan(country="CL"), limit=3)

    headings = [line for line in lines if line.startswith(f"  {OutcomeKind.DISABLED.value} — ")]
    assert len(headings) == 1, "one shared reason is written once, not per channel"
    assert sum(1 for line in lines if line.startswith("    - c")) == 3
    assert "    … 22 more (--limit 0 lists them all)" in lines

    everything = render_discovery_plan(service.plan(country="CL"), limit=0)
    assert sum(1 for line in everything if line.startswith("    - c")) == 25
    assert not [line for line in everything if "more (--limit" in line]


def test_the_registry_only_runs_factories_it_was_given() -> None:
    """Data names an adapter key; it never names code to import."""
    registry = AdapterKeyRegistry({"demo_adapter": lambda channel: StubSource([_posting()])})

    assert registry.keys == ("demo_adapter",)
    assert registry.resolve(_channel()).search_jobs(QUERY)

    for channel in (_channel(adapter_key=None), _channel(adapter_key="inventado")):
        try:
            registry.resolve(channel)
        except UnsupportedSourceError as exc:
            assert channel.channel_id in str(exc)
        else:  # pragma: no cover - the registry must refuse both
            raise AssertionError("an unknown adapter key must not resolve")
