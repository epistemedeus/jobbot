"""A listing's identity lives in its query too: keep the tenant, drop the tracking."""

from __future__ import annotations

import pytest

from jobbot.companies.urls import (
    PrivateRouteRejected,
    canonical_key,
    semantic_key,
    semantic_url,
)


def test_tracking_is_dropped_and_the_tenant_survives() -> None:
    """`public_url` throws the whole query away; a tenant in the query must not go with it."""
    url = "https://ats-demo.com/ux/ats/careersite/5/home?c=empresa-demo&utm_source=linkedin&trk=x"

    assert semantic_url(url) == "https://ats-demo.com/ux/ats/careersite/5/home?c=empresa-demo"
    assert canonical_key(url) == "ats-demo.com/ux/ats/careersite/5/home"


def test_two_tenants_on_one_host_are_two_channels() -> None:
    """Dedup by host alone would merge every employer sharing an ATS instance."""
    one = semantic_key("https://ats-demo.com/career?company=EMPRESA1")
    other = semantic_key("https://ats-demo.com/career?company=EMPRESA2")

    assert one != other


def test_the_key_ignores_www_a_trailing_slash_and_parameter_order() -> None:
    first = semantic_key("https://WWW.empresa-demo.cl/empleos/?b=2&a=1")
    second = semantic_key("http://empresa-demo.cl/empleos?a=1&b=2")

    assert first == second == "empresa-demo.cl/empleos?a=1&b=2"


def test_the_canonical_url_keeps_the_host_the_portal_published() -> None:
    """Some hosts only answer on www; the key normalizes, the stored URL does not."""
    assert semantic_url("https://www.empresa-demo.cl/trabaja") == (
        "https://www.empresa-demo.cl/trabaja"
    )


def test_an_empty_search_parameter_is_kept() -> None:
    """`?q=&sortColumn=…` is the portal's own search form, not noise."""
    assert semantic_url("https://empleos-demo.com/go/?q=&sortColumn=sort_title") == (
        "https://empleos-demo.com/go/?q=&sortColumn=sort_title"
    )


def test_a_bracketed_country_filter_survives_encoding() -> None:
    url = "https://empleos-demo.com/empleos?countries%5B%5D=Chile"

    assert semantic_url(url) == url


@pytest.mark.parametrize("route", ["mailto:rrhh@empresa-demo.cl", "", "not a url"])
def test_routes_that_are_not_a_public_page_are_refused(route: str) -> None:
    with pytest.raises(PrivateRouteRejected):
        semantic_url(route)
