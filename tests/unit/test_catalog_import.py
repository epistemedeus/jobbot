"""Importing researched sources: reproduce the counts, lose nothing, enable nothing."""

from __future__ import annotations

from datetime import date

import pytest

from jobbot.catalog.models import Capability, CapabilityStatus, ChannelRelation, SourceType
from jobbot.catalog.registry import ChannelNotEnabled, SourceCatalog, diff_catalogs
from jobbot.catalog.seed import (
    IssueLevel,
    SeedChannel,
    SeedDocument,
    SeedExpectations,
    import_seed,
)

LISTING = "listing"


def _seed(*rows: SeedChannel, expected: SeedExpectations | None = None, **kwargs: object) -> (
    SeedDocument
):
    payload: dict[str, object] = {
        "country": "CL",
        "researched_at": date(2026, 10, 12),
        "channels": list(rows),
        **kwargs,
    }
    if expected is not None:
        payload["expected"] = expected
    return SeedDocument.model_validate(payload)


def _row(**kwargs: object) -> SeedChannel:
    base: dict[str, object] = {
        "employer": "Empresa Demo",
        "url": "https://empresa-demo.cl/empleos",
        "sector": "demo",
        "type": LISTING,
        "ats": "unknown",
        "read": "fetched",
    }
    base.update(kwargs)
    return SeedChannel.model_validate(base)


def test_the_counts_the_research_declared_are_reproduced() -> None:
    seed = _seed(
        _row(),
        _row(employer="Otra Demo", url="https://otra-demo.cl/vacantes", ats="trabajando"),
        _row(
            employer="Otra Demo",
            url="https://otra-demo.cl/cv",
            type="cv_inbox",
            read="js_required",
        ),
        expected=SeedExpectations(
            employers=2,
            channels=3,
            sectors=1,
            by_type={"listing": 2, "cv_inbox": 1},
            by_read={"fetched": 2, "js_required": 1},
        ),
    )

    catalog, report = import_seed(seed)

    assert report.ok
    assert report.mismatches == ()
    assert (report.employers, report.channels, report.sectors) == (2, 3, 1)
    assert len(catalog.channels) == 3
    assert len(catalog.links) == 3


def test_a_count_that_does_not_match_stops_the_import() -> None:
    """A silent loss of sources is the failure mode this file exists to prevent."""
    seed = _seed(_row(), expected=SeedExpectations(channels=2))

    _catalog, report = import_seed(seed)

    assert not report.ok
    assert report.mismatches == ("channels: declared 2, imported 1",)


def test_nothing_arrives_enabled_even_when_the_seed_asks() -> None:
    seed = _seed(_row(enabled=True, ats="lever"))

    catalog, report = import_seed(seed)

    assert [c.enabled for c in catalog.channels] == [False]
    assert any(issue.level is IssueLevel.ERROR for issue in report.issues)
    assert not report.ok


def test_a_known_ats_does_not_enable_a_channel() -> None:
    """Belonging to a vendor JobBot can read is not evidence about *this* channel."""
    catalog, _report = import_seed(_seed(_row(ats="lever")))
    channel = catalog.channels[0]

    with pytest.raises(ChannelNotEnabled):
        catalog.enable(channel.channel_id)

    channel.assess(
        Capability.JOB_LISTING,
        CapabilityStatus.SUPPORTED,
        reason="read 12 vacancies from a stored fixture",
    )
    assert catalog.enable(channel.channel_id).enabled


def test_a_documentation_domain_is_reported_not_stored() -> None:
    seed = _seed(_row(), _row(employer="Fixture", url="https://empresa.example.com/jobs"))

    catalog, report = import_seed(seed)

    assert [c.canonical_url for c in catalog.channels] == ["https://empresa-demo.cl/empleos"]
    assert any("reserved" in issue.reason for issue in report.errors)


def test_the_same_url_under_two_brands_is_one_channel_with_two_employers() -> None:
    """A group channel publishing for its subsidiaries must not become two channels."""
    seed = _seed(
        _row(employer="Grupo Demo", url="https://grupo-demo.cl/empleos"),
        _row(
            employer="Filial Demo",
            url="https://www.grupo-demo.cl/empleos/?utm_source=linkedin",
            relation=ChannelRelation.GROUP,
        ),
    )

    catalog, report = import_seed(seed)

    assert len(catalog.channels) == 1
    channel = catalog.channels[0]
    assert {e.name for e in catalog.employers_of(channel.channel_id)} == {
        "Grupo Demo",
        "Filial Demo",
    }
    assert report.shared_channels[0][0] == channel.channel_id
    assert report.duplicates


def test_two_employers_on_the_same_ats_keep_their_own_channel() -> None:
    seed = _seed(
        _row(employer="Una Demo", url="https://ats-demo.com/una-demo", ats="hiringroom"),
        _row(employer="Otra Demo", url="https://ats-demo.com/otra-demo", ats="hiringroom"),
    )

    catalog, _report = import_seed(seed)

    assert len({c.channel_id for c in catalog.channels}) == 2
    assert {c.platform.ats_family for c in catalog.channels} == {"hiringroom"}
    assert len(catalog.employers) == 2


def test_one_employer_with_two_platforms_keeps_both() -> None:
    seed = _seed(
        _row(url="https://ats-demo.com/empresa-demo", ats="hiringroom"),
        _row(url="https://otro-ats-demo.com/empresa-demo", ats="teamtailor"),
    )

    catalog, _report = import_seed(seed)
    employer = catalog.find_employer("Empresa Demo")
    assert employer is not None

    channels = catalog.channels_of(employer.employer_id)
    assert {c.platform.ats_family for c in channels} == {"hiringroom", "teamtailor"}


def test_an_intermediary_is_not_confused_with_the_employer() -> None:
    seed = _seed(
        _row(
            employer="Selectora Demo",
            url="https://ats-demo.com/selectora-demo",
            relation=ChannelRelation.INTERMEDIARY,
        )
    )

    catalog, _report = import_seed(seed)
    link = catalog.links[0]

    assert link.relation is ChannelRelation.INTERMEDIARY


def test_a_reading_failure_is_kept_as_a_failure() -> None:
    """A 403 is not "no vacancies": the state and the error stay on the channel."""
    seed = _seed(
        _row(read="reader_error"),
        _row(url="https://empresa-demo.cl/js", read="js_required"),
    )

    catalog, _report = import_seed(seed)
    states = {c.health.last_read_state.value: c for c in catalog.channels}

    assert set(states) == {"reader_error", "js_required"}
    assert states["reader_error"].health.last_error
    assert states["reader_error"].health.last_successful_fetch_at is None


def test_every_channel_carries_a_date_and_an_evidence_url() -> None:
    catalog, _report = import_seed(_seed(_row(source="https://empresa-demo.cl/trabaja")))
    channel = catalog.channels[0]

    assert channel.health.researched_at is not None
    assert channel.platform.evidence_url == "https://empresa-demo.cl/trabaja"
    assert channel.linked_from == "https://empresa-demo.cl/trabaja"


def test_a_spanish_cl_domain_is_not_a_hiring_country() -> None:
    """Country comes from the research, never from the TLD or the language."""
    seed = SeedDocument.model_validate({"channels": [_row()], "researched_at": date(2026, 10, 12)})

    catalog, _report = import_seed(seed)

    assert catalog.channels[0].country is None


def test_the_import_does_not_touch_the_catalog_it_was_given() -> None:
    """`--dry-run` is only honest if the import itself writes nothing in place."""
    catalog = SourceCatalog()

    updated, report = import_seed(_seed(_row()), catalog)

    assert catalog.channels == []
    assert len(updated.channels) == 1
    assert report.diff.added_channels


def test_importing_twice_changes_nothing_the_second_time() -> None:
    seed = _seed(_row())

    once, _report = import_seed(seed)
    twice, second = import_seed(seed, once)

    assert diff_catalogs(once, twice).is_empty
    assert second.duplicates


def test_a_second_sighting_reports_a_platform_change_instead_of_overwriting() -> None:
    seed = _seed(
        _row(ats="trabajando"),
        _row(ats="teamtailor"),
    )

    catalog, report = import_seed(seed)

    assert catalog.channels[0].platform.ats_family == "trabajando"
    assert any("ats changed" in issue.reason for issue in report.issues)


def test_the_research_queue_never_becomes_a_channel() -> None:
    seed = _seed(_row(), research_queue={"demo": ["Marca Pendiente", "Otra Pendiente"]})

    catalog, report = import_seed(seed)

    assert report.research_queue == 2
    assert len(catalog.channels) == 1
    assert [e.name for e in catalog.employers] == ["Empresa Demo"]


def test_an_access_page_is_not_filed_as_a_listing() -> None:
    catalog, _report = import_seed(_seed(_row(type="access")))

    assert catalog.channels[0].source_type is SourceType.ACCESS
