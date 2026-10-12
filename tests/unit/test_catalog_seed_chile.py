"""The shipped Chilean inventory must import whole, disabled, and without mixing anyone up."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import pytest

from jobbot.catalog.composition import default_source_registry
from jobbot.catalog.coverage import measure_coverage
from jobbot.catalog.models import ChannelRelation, ReadState, SourceType
from jobbot.catalog.registry import SourceCatalog
from jobbot.catalog.seed import ImportReport, import_seed, load_seed
from jobbot.config import JobbotConfig

SEED = Path("data") / "sources-cl.example.yaml"


def _config() -> JobbotConfig:
    """The adapter keys that exist today; the catalog never invents one."""
    return JobbotConfig()


@lru_cache(maxsize=1)
def _imported(root: str) -> tuple[SourceCatalog, ImportReport]:
    """Importing 249 channels once is enough; no test below writes to the catalog."""
    return import_seed(load_seed(Path(root) / SEED))


@pytest.fixture
def imported(project_root: Path) -> tuple[SourceCatalog, ImportReport]:
    return _imported(str(project_root))


def test_the_inventory_imports_with_the_counts_it_declares(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, report = imported

    assert report.ok, report.mismatches + tuple(i.reason for i in report.errors)
    assert (report.employers, report.channels, report.sectors) == (194, 249, 15)
    assert report.by_type == {"listing": 195, "access": 47, "cv_inbox": 5, "job_posting": 2}
    assert report.by_read == {
        "fetched": 204,
        "js_required": 14,
        "no_content": 4,
        "reader_error": 26,
        "pending_destination": 1,
    }
    assert len(catalog.channels) == 249
    assert len(catalog.links) == 249


def test_the_pending_brands_stay_out_of_the_catalog(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    """257 names with no verified channel are research, not portals."""
    catalog, report = imported

    assert report.research_queue == 257
    assert len(catalog.employers) == 194


def test_no_channel_is_enabled(imported: tuple[SourceCatalog, ImportReport]) -> None:
    catalog, _report = imported

    assert not any(channel.enabled for channel in catalog.channels)


def test_every_channel_has_a_unique_id_a_valid_url_and_a_date(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported

    assert len({c.channel_id for c in catalog.channels}) == len(catalog.channels)
    assert len({c.key for c in catalog.channels}) == len(catalog.channels)
    for channel in catalog.channels:
        parsed = urlparse(channel.canonical_url)
        assert parsed.scheme in {"http", "https"}
        assert parsed.hostname and "." in parsed.hostname
        assert channel.health.researched_at is not None
        assert channel.platform.evidence_url


def test_a_bank_and_its_insurer_are_two_employers(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported
    bank = catalog.find_employer("Bci")
    insurer = catalog.find_employer("BCI Seguros")

    assert bank is not None and insurer is not None
    assert bank.employer_id != insurer.employer_id


def test_a_bank_keeps_every_channel_and_its_subsidiaries_keep_their_own(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported
    parent = catalog.find_employer("BancoEstado")
    assert parent is not None

    assert len(catalog.channels_of(parent.employer_id)) >= 2
    subsidiary = catalog.find_employer("BancoEstado CajaVecina")
    assert subsidiary is not None
    assert subsidiary.employer_id != parent.employer_id


def test_a_recruiter_channel_is_marked_as_an_intermediary(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported
    agency = catalog.find_employer("Adecco Chile")
    assert agency is not None

    relations = {link.relation for link in catalog.links if link.employer_id == agency.employer_id}
    assert relations == {ChannelRelation.INTERMEDIARY}


def test_a_404_on_a_linked_portal_is_a_reading_failure_not_a_closed_portal(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported
    channel = catalog.find_channel("https://copec.hiringroom.com/jobs")

    assert channel is not None
    assert channel.health.last_read_state is ReadState.READER_ERROR
    assert channel.health.replaced_by is None
    assert channel.linked_from  # the corporate page that still links it


def test_a_tenant_in_the_query_is_part_of_the_channel(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported
    channel = catalog.find_channel("https://cencosud.csod.com/ux/ats/careersite/5/home?c=cencosud")

    assert channel is not None
    assert channel.canonical_url.endswith("?c=cencosud")


def test_tracking_in_the_evidence_link_never_reaches_the_stored_url(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported

    for channel in catalog.channels:
        assert "utm_" not in channel.canonical_url
        assert "trk=" not in channel.canonical_url


def test_a_general_cv_form_is_not_a_vacancy_listing(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported
    inboxes = [c for c in catalog.channels if c.source_type is SourceType.CV_INBOX]

    assert len(inboxes) == 5
    assert all(c.platform.adapter_key is None for c in catalog.channels)


def test_the_ats_family_is_an_observation_not_a_capability(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    """Vendors JobBot has no adapter for are recorded as what the page showed."""
    catalog, _report = imported
    families = {c.platform.ats_family for c in catalog.channels}

    assert {"trabajando", "hiringroom", "aira", "pandape", "luk"} <= families
    assert all(c.capabilities == [] for c in catalog.channels)


def test_the_inventory_is_the_denominator_of_the_coverage_indicator(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    """The list is official the day it measures us: 249 channels, reach still 0%."""
    catalog, _report = imported

    report = measure_coverage(catalog, country="CL", adapters=default_source_registry(_config()))

    assert (report.total.channels, report.total.employers) == (249, 194)
    assert report.total.reach_pct == 0.0
    assert report.total.presence_pct == 0.0
    assert report.total.pending == 249


def test_the_indicator_orders_the_work_by_how_many_channels_it_unlocks(
    imported: tuple[SourceCatalog, ImportReport],
) -> None:
    catalog, _report = imported

    report = measure_coverage(catalog, country="CL")
    unlocks = {group.label: group.channels for group in report.unlocks}

    assert unlocks["trabajando"] == 60
    assert [g.label for g in report.unlocks][:3] == ["trabajando", "aira", "hiringroom"]
    assert report.unidentified is not None
    assert report.unidentified.channels == 92
