"""Human-readable reports for the catalog import and the discovery dry run."""

from __future__ import annotations

from collections.abc import Mapping

from jobbot.catalog.coverage import CoverageReport
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


def render_coverage(report: CoverageReport, *, by: str = "ats", limit: int = 10) -> list[str]:
    """The indicator: the denominator first, then what JobBot reaches and what is proven."""
    total = report.total
    scope = report.country or "any country"
    lines = [
        f"Catalog coverage — {scope} · catalog {report.catalog_version} "
        f"· capability {report.capability.value}",
        f"  channels        : {total.channels} ({total.employers} employers)",
        f"  JobBot reach    : {total.reach_pct}% — {total.proven} proven, "
        f"{total.wired} wired, {total.pending} pending",
        f"  your presence   : {total.presence_pct}% — {total.present} of {total.channels} "
        "with local evidence",
    ]
    groups = report.by_sector if by == "sector" else report.by_ats
    heading = "by sector" if by == "sector" else "by platform"
    lines.append(f"  {heading}:")
    shown = groups if limit <= 0 else groups[:limit]
    for group in shown:
        lines.append(
            f"    {group.label:<16} {group.channels:>4} channels "
            f"{group.employers:>4} employers  reach {group.reach_pct:>5}%  "
            f"presence {group.presence_pct:>5}%"
        )
    hidden = len(groups) - len(shown)
    if hidden:
        lines.append(f"    … {hidden} more (--limit 0 lists them all)")
    unlocks = report.unlocks if limit <= 0 else report.unlocks[:3]
    if unlocks:
        lines.append("  next unlock (no adapter yet):")
        for group in unlocks:
            lines.append(
                f"    {group.label:<16} would unlock {group.channels} channels "
                f"({_share(group.channels, total.channels)}% of the catalog), "
                f"{group.employers} employers"
            )
    unknown = report.unidentified
    if unknown is not None:
        lines.append(
            f"  unidentified    : {unknown.channels} channels "
            f"({_share(unknown.channels, total.channels)}%) have no platform named yet "
            "— jobbot companies recon"
        )
    lines.append(
        "  Presence counts evidence only: a channel with no receipt is unverified, "
        "not absent."
    )
    return lines


def coverage_headline(report: CoverageReport) -> str:
    """One line for `jobbot status`: the denominator never travels without its percentages."""
    total = report.total
    scope = report.country or "catalog"
    return (
        f"{scope}: {total.channels} channels · JobBot reach {total.reach_pct}% "
        f"· your presence {total.presence_pct}% (jobbot portals catalog coverage)"
    )


def render_discovery_plan(report: DiscoveryReport, *, limit: int = 10) -> list[str]:
    """Which sources could be explored, which need review, and why. Creates nothing."""
    lines = [f"Discovery plan — country {report.country or 'any'} (dry run, nothing read)"]
    counts = report.counts
    lines.append(f"  explorable now : {counts.get(OutcomeKind.READY.value, 0)}")
    for kind, count in sorted(counts.items()):
        if kind != OutcomeKind.READY.value:
            lines.append(f"  {kind:<16}: {count}")
    grouped: dict[tuple[str, str], list[str]] = {}
    for outcome in report.needs_review:
        grouped.setdefault((outcome.kind.value, outcome.reason), []).append(outcome.channel_id)
    for (kind, reason), channel_ids in sorted(grouped.items()):
        lines.append(f"  {kind} — {reason}")
        shown = channel_ids if limit <= 0 else channel_ids[:limit]
        lines.extend(f"    - {channel_id}" for channel_id in shown)
        hidden = len(channel_ids) - len(shown)
        if hidden:
            lines.append(f"    … {hidden} more (--limit 0 lists them all)")
    lines.append("  No account was created and no application was sent.")
    return lines


def _share(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def _counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "—"
    return ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))
