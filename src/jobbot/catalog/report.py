"""Human-readable reports for the catalog import and the discovery dry run."""

from __future__ import annotations

from collections.abc import Mapping

from jobbot.catalog.discovery import DiscoveryReport, OutcomeKind
from jobbot.catalog.models import Channel
from jobbot.catalog.registry import SourceCatalog
from jobbot.catalog.seed import ImportReport


def render_import_report(report: ImportReport, *, applied: bool) -> list[str]:
    lines: list[str] = []
    header = "imported" if applied else "dry-run (nothing written)"
    lines.append(f"Source catalog import — {header}")
    if report.researched_at:
        lines.append(f"  researched_at : {report.researched_at.isoformat()}")
    if report.country:
        lines.append(f"  country       : {report.country}")
    lines.append(
        f"  read          : {report.employers} employers, {report.channels} channels, "
        f"{report.sectors} sectors"
    )
    lines.append("  by type       : " + _counts(report.by_type))
    lines.append("  by read state : " + _counts(report.by_read))
    if report.research_queue:
        lines.append(
            f"  research queue: {report.research_queue} brands with no verified channel "
            "(hypotheses, not portals)"
        )
    lines.append("  enabled       : 0 (a seeded channel is a candidate)")

    for mismatch in report.mismatches:
        lines.append(f"  ! count mismatch — {mismatch}")
    for issue in report.issues:
        lines.append(f"  ! {issue.level.value}: {issue.subject} — {issue.reason}")
    for url, channel_id in report.duplicates:
        lines.append(f"  = duplicate canonical URL merged into {channel_id}: {url}")
    for channel_id, employers in report.shared_channels:
        lines.append(f"  ~ shared channel {channel_id}: {', '.join(employers)}")

    diff = report.diff
    lines.append(
        "  diff          : "
        f"+{len(diff.added_employers)} employers, +{len(diff.added_channels)} channels, "
        f"+{len(diff.added_links)} links, ~{len(diff.changed_channels)} changed"
    )
    for channel_id, label in diff.changed_channels:
        lines.append(f"    ~ {channel_id}: {label}")
    if not applied:
        lines.append("  Run again with --apply to write the catalog.")
    return lines


def render_catalog_list(catalog: SourceCatalog, channels: list[Channel]) -> list[str]:
    lines: list[str] = []
    for channel in channels:
        employers = ", ".join(e.name for e in catalog.employers_of(channel.channel_id)) or "—"
        state = channel.health.last_read_state.value
        lines.append(
            f"{channel.channel_id:<48} {channel.source_type.value:<12} "
            f"{channel.platform.ats_family:<14} {state:<20} {employers}"
        )
    return lines


def render_discovery_plan(report: DiscoveryReport) -> list[str]:
    """Which sources could be explored, which need review, and why. Creates nothing."""
    lines = [f"Discovery plan — country {report.country or 'any'} (dry run, nothing read)"]
    counts = report.counts
    ready = counts.get(OutcomeKind.READY.value, 0)
    lines.append(f"  explorable now : {ready}")
    for kind, count in sorted(counts.items()):
        if kind != OutcomeKind.READY.value:
            lines.append(f"  {kind:<16}: {count}")
    for outcome in report.needs_review:
        lines.append(f"  - {outcome.channel_id} [{outcome.kind.value}] {outcome.reason}")
    lines.append("  No account was created and no application was sent.")
    return lines


def _counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "—"
    return ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))
