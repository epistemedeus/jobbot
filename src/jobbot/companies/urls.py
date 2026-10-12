"""URL normalization for shareable career-site knowledge (no personal tokens)."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse


class PrivateRouteRejected(ValueError):
    """Raised when a URL cannot be shared as company knowledge (e.g. mailto:)."""


class ReservedDomainRejected(PrivateRouteRejected):
    """Raised for documentation/test domains: they are fixtures, never an employer."""


# RFC 2606 / RFC 6761 names reserved for documentation and testing.
_RESERVED_DOMAINS: frozenset[str] = frozenset({"example.com", "example.net", "example.org"})
_RESERVED_TLDS: frozenset[str] = frozenset({"example", "test", "invalid", "localhost"})


# Suffixes where the registrable domain needs three labels (empresa.com.ar).
_MULTI_SUFFIXES: frozenset[str] = frozenset(
    {
        "com.ar",
        "com.au",
        "com.br",
        "com.co",
        "com.mx",
        "com.pe",
        "com.uy",
        "com.ve",
        "co.uk",
        "co.il",
        "co.nz",
        "com.tr",
    }
)

# Prefixes companies stick in front of their own name for career hosts.
_CAREER_NAME_PREFIXES: tuple[str, ...] = (
    "trabajaen",
    "trabaja-en",
    "trabajacon",
    "trabaja",
    "careers",
    "career",
    "jobs",
    "empleos",
    "empleo",
    "talento",
    "vacantes",
)


def public_url(url: str) -> str:
    """Normalize to a shareable URL: no credentials, no query, no fragment.

    Query strings and fragments are dropped on purpose: they are where portals put
    session ids, referral tokens and per-application parameters.
    """
    raw = (url or "").strip()
    if not raw:
        msg = "empty URL"
        raise PrivateRouteRejected(msg)
    if raw.lower().startswith("mailto:"):
        msg = "email apply routes are personal data, not company knowledge"
        raise PrivateRouteRejected(msg)
    if not re.match(r"^https?://", raw, re.I):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        msg = f"URL without host: {url!r}"
        raise PrivateRouteRejected(msg)
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    scheme = parsed.scheme.lower() if parsed.scheme in {"http", "https"} else "https"
    return urlunparse((scheme, netloc, path, "", "", ""))


def canonical_key(url: str) -> str:
    """Dedup key: scheme-insensitive host + path (already query/fragment free)."""
    normalized = public_url(url)
    parsed = urlparse(normalized)
    return f"{parsed.netloc}{parsed.path}".casefold()


# Parameters identified as tracking, each one seen on a career link we stored:
# share referrers (``source=linkedin``, ``src``), campaign ids (``utm_*``, ``icid``),
# ad click ids and LinkedIn's per-member ``rcm`` / ``trk``. Everything else is kept:
# a query string is also where a portal puts the tenant, the country and the search.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "_ga",
        "fbclid",
        "gclid",
        "icid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "rcm",
        "ref_src",
        "referrer",
        "source",
        "spm",
        "src",
        "trackingid",
        "trk",
        "trkcampaignid",
    }
)
_TRACKING_PREFIXES: tuple[str, ...] = ("utm_",)


def is_tracking_param(name: str) -> bool:
    folded = (name or "").strip().casefold()
    return folded in _TRACKING_PARAMS or folded.startswith(_TRACKING_PREFIXES)


def semantic_url(url: str) -> str:
    """
    Shareable URL that keeps the query a portal needs and drops the tracking it does not.

    ``public_url`` throws the whole query away, which is right for a career portal whose
    identity is its path. It is wrong for a listing whose tenant, country or site lives in
    the query (``?c=cencosud``, ``?company=AMSAP``, ``?countries[]=Chile``): dropping those
    turns a listing into somebody else's.
    """
    raw = (url or "").strip()
    if not raw:
        msg = "empty URL"
        raise PrivateRouteRejected(msg)
    if raw.lower().startswith("mailto:"):
        msg = "email apply routes are personal data, not company knowledge"
        raise PrivateRouteRejected(msg)
    if not re.match(r"^https?://", raw, re.I):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host:
        msg = f"URL without host: {url!r}"
        raise PrivateRouteRejected(msg)
    # A catalog row is typed by a human: "empresa demo" is a note, not a host.
    if any(ch.isspace() for ch in host) or "." not in host:
        msg = f"not a host name: {host!r} (from {url!r})"
        raise PrivateRouteRejected(msg)
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "")
    scheme = parsed.scheme.lower() if parsed.scheme in {"http", "https"} else "https"
    kept = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not is_tracking_param(name)
    ]
    query = urlencode(kept, quote_via=quote)
    return urlunparse((scheme, netloc, path, "", query, ""))


def semantic_key(url: str) -> str:
    """
    Dedup key that survives ``www.``, a trailing slash and parameter order.

    Two tenants can share a host (``jobs.airavirtual.com/<tenant>``), so the key keeps the
    path and the semantic query; only identified tracking is dropped.
    """
    parsed = urlparse(semantic_url(url))
    host = (parsed.hostname or "").removeprefix("www.")
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    path = (parsed.path or "").rstrip("/")
    params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    query = urlencode(params, quote_via=quote)
    return f"{netloc}{path}{'?' + query if query else ''}".casefold()


def host_of(url: str) -> str:
    return urlparse(public_url(url)).netloc.split(":", 1)[0]


def display_url(url: str) -> str:
    """Host plus path, the part a reviewer reads; the scheme carries nothing."""
    return re.sub(r"^https?://", "", public_url(url), flags=re.I)


def is_reserved_host(host: str) -> bool:
    """True for example/test/invalid/localhost names, which no employer can own."""
    labels = (host or "").strip().casefold().rstrip(".").split(".")
    if not labels or not labels[-1]:
        return False
    if labels[-1] in _RESERVED_TLDS:
        return True
    return ".".join(labels[-2:]) in _RESERVED_DOMAINS


def ensure_not_reserved(url: str) -> str:
    """Normalized URL, or ReservedDomainRejected when its host is a fixture name."""
    normalized = public_url(url)
    host = host_of(normalized)
    if is_reserved_host(host):
        msg = f"{host} is a reserved example/test domain, not a company portal; not stored"
        raise ReservedDomainRejected(msg)
    return normalized


def registrable_domain(host: str) -> str:
    """Best-effort eTLD+1 without a public suffix list (good enough for dedup hints)."""
    labels = (host or "").lower().removeprefix("www.").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in _MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def slugify(text: str) -> str:
    """Stable company id from a display name."""
    lowered = (text or "").strip().casefold()
    lowered = (
        lowered.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:60]


# Generic labels ATS vendors use, so they never name the employer.
_VENDOR_LABELS: frozenset[str] = frozenset(
    {
        "apply",
        "boards",
        "career",
        "career5",
        "careers",
        "job-boards",
        "jobs",
        "performancemanager",
        "www",
    }
)


def company_hint_from_url(url: str) -> str:
    """Guess a company slug from a career host (fallback only, never a fact)."""
    from jobbot.portals.detect import AtsKind, detect_ats

    host = host_of(url)
    if detect_ats(url) not in {AtsKind.UNKNOWN, AtsKind.EMAIL}:
        return _hint_from_ats_url(url, host)
    label = registrable_domain(host).split(".")[0]
    subdomain = host.removesuffix(registrable_domain(host)).strip(".")
    for candidate in (label, subdomain):
        name = candidate
        for prefix in _CAREER_NAME_PREFIXES:
            if name.startswith(prefix) and len(name) > len(prefix) + 1:
                name = name[len(prefix) :].strip("-")
        if name and name not in _CAREER_NAME_PREFIXES:
            return slugify(name)
    return slugify(label)


def _hint_from_ats_url(url: str, host: str) -> str:
    """On an ATS, the employer is the tenant subdomain or the board path segment."""
    tenant = host.split(".")[0]
    if tenant not in _VENDOR_LABELS and not re.fullmatch(r"wd\d+", tenant):
        return slugify(tenant)
    segments = [seg for seg in urlparse(public_url(url)).path.split("/") if seg]
    return slugify(segments[0]) if segments else slugify(tenant)
