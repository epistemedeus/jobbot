"""The composition root wires real adapters; having one still does not enable a channel."""

from __future__ import annotations

from jobbot.catalog.composition import build_discovery_service, default_source_registry
from jobbot.catalog.discovery import OutcomeKind, UnsupportedSourceError
from jobbot.catalog.models import Channel, PlatformBinding, SourceType
from jobbot.catalog.registry import SourceCatalog, diff_catalogs
from jobbot.config import JobbotConfig


def _channel(ats: str, *, adapter_key: str | None, enabled: bool = True) -> Channel:
    return Channel(
        channel_id=f"{ats}-demo",
        entry_url="https://empresa-demo.cl/empleos",
        canonical_url="https://empresa-demo.cl/empleos",
        source_type=SourceType.LISTING,
        enabled=enabled,
        country="CL",
        platform=PlatformBinding(ats_family=ats, adapter_key=adapter_key),
    )


def test_the_registry_offers_the_adapters_that_exist_today() -> None:
    registry = default_source_registry(JobbotConfig())

    assert set(registry.keys) == {
        "indeed",
        "linkedin_post",
        "getonboard",
        "torre",
        "empleos_publicos",
    }


def test_an_observed_vendor_without_an_adapter_is_an_unsupported_source() -> None:
    """`ats_family: trabajando` is what the page showed, not a key the registry must honour."""
    registry = default_source_registry(JobbotConfig())

    try:
        registry.resolve(_channel("trabajando", adapter_key=None))
    except UnsupportedSourceError as exc:
        assert "trabajando" in str(exc)
    else:  # pragma: no cover - resolving an unimplemented vendor would be the bug
        raise AssertionError("an un-implemented vendor must not resolve")


def test_an_implemented_adapter_does_not_enable_a_candidate_channel() -> None:
    catalog = SourceCatalog(channels=[_channel("indeed", adapter_key="indeed", enabled=False)])
    service = build_discovery_service(JobbotConfig(), catalog)

    report = service.plan(country="CL")

    assert report.outcomes[0].kind is OutcomeKind.DISABLED


def test_a_plan_over_an_enabled_channel_stops_at_the_access_policy() -> None:
    """No capability was recorded, so the default policy answers unknown — and nothing runs."""
    catalog = SourceCatalog(channels=[_channel("indeed", adapter_key="indeed")])
    service = build_discovery_service(JobbotConfig(), catalog)

    outcome = service.plan(country="CL").outcomes[0]

    assert outcome.kind is OutcomeKind.NEEDS_REVIEW
    assert "job_listing unknown" in outcome.reason


def test_the_diff_names_what_a_review_has_to_look_at() -> None:
    before = SourceCatalog(channels=[_channel("indeed", adapter_key=None, enabled=False)])
    after = before.model_copy(deep=True)
    after.channels[0].platform.ats_family = "lever"
    after.channels[0].enabled = True
    after.channels.append(_channel("otro", adapter_key=None))

    diff = diff_catalogs(before, after)

    assert diff.added_channels == ("otro-demo",)
    labels = [label for _channel_id, label in diff.changed_channels]
    assert "ats: indeed → lever" in labels
    assert "enabled: False → True" in labels
    assert diff_catalogs(after, before).removed_channels == ("otro-demo",)
