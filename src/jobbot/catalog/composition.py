"""Composition root: the one place that wires repository, policy and registry together.

The domain never imports a concrete adapter, and there is no global lookup: the CLI (or a
test) builds the parts here and hands them to :class:`DiscoveryService`.
"""

from __future__ import annotations

from jobbot.catalog.discovery import (
    AccessPolicy,
    AdapterFactory,
    AdapterKeyRegistry,
    CapabilityAccessPolicy,
    CatalogChannelRepository,
    ChannelRepository,
    DiscoveryService,
    SourceRegistry,
)
from jobbot.catalog.models import Channel
from jobbot.catalog.registry import SourceCatalog
from jobbot.config import JobbotConfig
from jobbot.jobs.sources import JobSourceAdapter, JobSourceName, get_job_source


def legacy_source_factory(name: JobSourceName, config: JobbotConfig) -> AdapterFactory:
    """Reuse ``get_job_source`` as a facade so existing adapters need no parallel hierarchy."""

    def factory(channel: Channel) -> JobSourceAdapter:
        del channel  # these adapters configure themselves from the global config
        return get_job_source(name, config)

    return factory


def default_source_registry(config: JobbotConfig) -> AdapterKeyRegistry:
    """Adapter keys that exist today. A key is a promise the catalog may not invent."""
    return AdapterKeyRegistry(
        {
            "indeed": legacy_source_factory("indeed", config),
            "linkedin_post": legacy_source_factory("linkedin_post", config),
            "getonboard": legacy_source_factory("getonboard", config),
            "torre": legacy_source_factory("torre", config),
            "empleos_publicos": legacy_source_factory("empleos_publicos", config),
        }
    )


def build_discovery_service(
    config: JobbotConfig,
    catalog: SourceCatalog,
    *,
    channels: ChannelRepository | None = None,
    sources: SourceRegistry | None = None,
    policy: AccessPolicy | None = None,
) -> DiscoveryService:
    return DiscoveryService(
        channels=channels or CatalogChannelRepository(catalog.channels),
        sources=sources or default_source_registry(config),
        policy=policy or CapabilityAccessPolicy(),
    )
