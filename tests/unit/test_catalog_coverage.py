"""Coverage is an indicator with a denominator: the catalog, never "all the portals"."""

from __future__ import annotations

from jobbot.catalog.coverage import ReachState, measure_coverage, reach_state
from jobbot.catalog.discovery import AdapterKeyRegistry
from jobbot.catalog.models import (
    Capability,
    CapabilityStatus,
    Channel,
    ChannelRelation,
    Employer,
    PlatformBinding,
    SourceType,
)
from jobbot.catalog.registry import SourceCatalog
from jobbot.catalog.report import coverage_headline, render_coverage


def _catalog() -> SourceCatalog:
    catalog = SourceCatalog()
    rows = [
        ("banco-demo", "Banco Demo", "banca", "banca-ats", "https://banco-demo.cl/empleos"),
        ("tienda-demo", "Tienda Demo", "retail", "banca-ats", "https://tienda-demo.cl/empleos"),
        ("mina-demo", "Mina Demo", "mineria", "otro-ats", "https://mina-demo.cl/empleos"),
    ]
    for employer_id, name, sector, family, url in rows:
        catalog.add_employer(
            Employer(employer_id=employer_id, name=name, sector=sector, country="CL")
        )
        channel = Channel(
            channel_id=f"{employer_id}-canal",
            entry_url=url,
            canonical_url=url,
            source_type=SourceType.LISTING,
            country="CL",
            platform=PlatformBinding(ats_family=family),
        )
        catalog.add_channel(channel)
        catalog.link(
            employer_id=employer_id,
            channel_id=channel.channel_id,
            relation=ChannelRelation.OWNER,
        )
    return catalog


def test_nothing_is_reachable_before_an_adapter_exists() -> None:
    report = measure_coverage(_catalog(), country="CL")

    assert report.total.channels == 3
    assert report.total.employers == 3
    assert (report.total.proven, report.total.wired, report.total.pending) == (0, 0, 3)
    assert report.total.reach_pct == 0.0


def test_a_registered_adapter_is_wired_and_a_probed_channel_is_proven() -> None:
    catalog = _catalog()
    for channel in catalog.channels:
        if channel.platform.ats_family == "banca-ats":
            channel.platform.adapter_key = "banca_adapter"
    catalog.channels[0].assess(
        Capability.JOB_LISTING,
        CapabilityStatus.SUPPORTED,
        reason="fixture read",
    )
    adapters = AdapterKeyRegistry({"banca_adapter": lambda channel: None})  # type: ignore[arg-type]

    report = measure_coverage(catalog, country="CL", adapters=adapters)

    assert (report.total.proven, report.total.wired, report.total.pending) == (1, 1, 1)
    assert report.total.reach_pct == 66.7


def test_belonging_to_a_known_ats_never_counts_as_reach() -> None:
    """The platform is an observation; without an adapter key nothing is wired."""
    catalog = _catalog()
    adapters = AdapterKeyRegistry({"banca_adapter": lambda channel: None})  # type: ignore[arg-type]

    report = measure_coverage(catalog, country="CL", adapters=adapters)

    assert report.total.reachable == 0
    assert all(
        reach_state(c, adapters=adapters) is ReachState.PENDING for c in catalog.channels
    )


def test_presence_counts_receipts_and_a_missing_one_is_not_absence() -> None:
    catalog = _catalog()
    receipt_key = catalog.channels[0].key

    report = measure_coverage(catalog, country="CL", presence={receipt_key: "page evidence"})

    assert (report.total.present, report.total.channels) == (1, 3)
    assert report.total.presence_pct == 33.3
    assert "evidence only" in " ".join(render_coverage(report)).casefold()


def test_the_country_filter_moves_the_denominator() -> None:
    catalog = _catalog()
    catalog.channels[0].country = "AR"

    assert measure_coverage(catalog, country="CL").total.channels == 2
    assert measure_coverage(catalog).total.channels == 3


def test_the_biggest_platform_with_no_adapter_is_the_next_unlock() -> None:
    report = measure_coverage(_catalog(), country="CL")

    unlocks = report.unlocks
    assert [g.label for g in unlocks] == ["banca-ats", "otro-ats"]
    assert (unlocks[0].channels, unlocks[0].employers) == (2, 2)
    assert "would unlock 2 channels" in "\n".join(render_coverage(report))


def test_a_channel_with_no_named_platform_is_recon_not_a_pending_adapter() -> None:
    catalog = _catalog()
    catalog.channels[0].platform.ats_family = "unknown"

    report = measure_coverage(catalog, country="CL")

    assert "unknown" not in [g.label for g in report.unlocks]
    assert report.unidentified is not None
    assert report.unidentified.channels == 1
    assert "jobbot companies recon" in "\n".join(render_coverage(report))


def test_a_shared_channel_is_counted_in_every_sector_it_serves() -> None:
    catalog = _catalog()
    catalog.add_employer(
        Employer(employer_id="marca-demo", name="Marca Demo", sector="moda", country="CL")
    )
    catalog.link(employer_id="marca-demo", channel_id="tienda-demo-canal")

    sectors = {g.label: g.channels for g in measure_coverage(catalog, country="CL").by_sector}

    assert sectors["retail"] == 1
    assert sectors["moda"] == 1


def test_the_headline_never_travels_without_its_denominator() -> None:
    line = coverage_headline(measure_coverage(_catalog(), country="CL"))

    assert "3 channels" in line
    assert "reach 0.0%" in line and "presence 0.0%" in line
