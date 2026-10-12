"""Write the permanent Get on Board profile through its own edit form.

Long blocks used to be Trix (``trix-editor`` + ``editor.loadHTML``). As of
2026-10 the portal serves Lexxy ``contenteditable`` nodes instead, synced to the
same hidden ``webpro[…]`` inputs. Each field tries both selectors; a missing
expected field is an error, never a silent skip. Reads come from the portal so
the plan can show what each field holds today.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from typing import Any, Protocol

logger = logging.getLogger("jobbot.getonboard.profile_edit")

GOB_EDIT_URL = "https://www.getonbrd.com/webpros/edit"
SAVE_BUTTON = 'input[type="submit"][value*="Guardar"]'
COUNTRY_SELECT = 'select[name="webpro[country]"]'
CV_REWRITE_NOTICE = (
    "Get on Board may rewrite the profile from the PDF («Estamos leyendo tu "
    "último CV…»). When that finishes, run `jobbot cv sync --apply` again."
)


class MissingGobFieldError(RuntimeError):
    """An expected edit-form field is gone — the portal markup likely changed."""

    def __init__(self, field: GobField) -> None:
        self.field = field
        super().__init__(f"campo no encontrado: {field.label} (¿cambió el portal?)")


class HiddenSyncError(RuntimeError):
    """Rich-text write did not reach the hidden input the form submits."""

    def __init__(self, field: GobField) -> None:
        self.field = field
        super().__init__(
            f"el editor no sincronizó el campo oculto: {field.label} (no se guardó)"
        )


@dataclass(frozen=True)
class GobField:
    """One editable field of the permanent profile."""

    key: str
    label: str
    selectors: tuple[str, ...]
    rich: bool
    hidden_selector: str | None = None

    @property
    def selector(self) -> str:
        """First selector (legacy / primary)."""
        return self.selectors[0]

    @property
    def trix(self) -> bool:
        """Back-compat alias: rich-text fields used to be Trix-only."""
        return self.rich


FIELDS: tuple[GobField, ...] = (
    GobField(
        key="description_es",
        label="Descripción profesional",
        selectors=('input[name="webpro[description_es]"]',),
        rich=False,
    ),
    GobField(
        key="professional_es",
        label="Perfil profesional y experiencia laboral",
        selectors=(
            "trix-editor#trix-professional_es",
            "#trix-professional_es-content[contenteditable]",
        ),
        rich=True,
        hidden_selector='input[name="webpro[professional_background_es]"]',
    ),
    GobField(
        key="academic_background_es",
        label="Formación académica y estudios",
        selectors=(
            "trix-editor#trix-academic_background_es",
            "#trix-academic_background_es-content[contenteditable]",
        ),
        rich=True,
        hidden_selector='input[name="webpro[academic_background_es]"]',
    ),
)


@dataclass(frozen=True)
class FieldWrite:
    """A pending change on one field, with the text the portal holds today."""

    field: GobField
    current: str
    new: str

    @property
    def verb(self) -> str:
        return "fill" if not self.current else "replace"

    def describe(self) -> str:
        if self.verb == "fill":
            return f"fill {self.field.label} ({len(self.new)} chars, empty today)"
        return (
            f"replace {self.field.label} "
            f"({len(self.current)} → {len(self.new)} chars)"
        )


@dataclass(frozen=True)
class LocatedField:
    """A field resolved to a concrete node on the page."""

    field: GobField
    element: ElementLike
    matched_selector: str

    @property
    def is_trix(self) -> bool:
        return matched_selector_is_trix(self.matched_selector)


def matched_selector_is_trix(selector: str) -> bool:
    return selector.casefold().startswith("trix-editor")


class ElementLike(Protocol):
    def inner_text(self) -> str: ...
    def input_value(self) -> str: ...
    def evaluate(self, expression: str, arg: Any = None) -> Any: ...
    def fill(self, value: str) -> None: ...
    def click(self) -> None: ...


class KeyboardLike(Protocol):
    def press(self, key: str) -> None: ...
    def insert_text(self, text: str) -> None: ...


class PageLike(Protocol):
    def goto(self, url: str, **kwargs: Any) -> Any: ...
    def query_selector(self, selector: str) -> ElementLike | None: ...
    def click(self, selector: str, **kwargs: Any) -> None: ...
    def wait_for_timeout(self, timeout: float) -> None: ...

    @property
    def keyboard(self) -> KeyboardLike: ...


def locate_field(page: PageLike, field: GobField) -> LocatedField | None:
    """First selector that matches, or None when the portal dropped the field."""
    for selector in field.selectors:
        element = page.query_selector(selector)
        if element is not None:
            return LocatedField(field=field, element=element, matched_selector=selector)
    return None


def absent_fields(page: PageLike) -> list[GobField]:
    return [field for field in FIELDS if locate_field(page, field) is None]


def read_current(page: PageLike) -> dict[str, str]:
    """What the portal shows right now, per field key ('' when empty).

    Missing fields are omitted — call ``absent_fields`` / ``require_fields`` to
    treat absence as an error instead of a silent skip.
    """
    out: dict[str, str] = {}
    for field in FIELDS:
        located = locate_field(page, field)
        if located is None:
            logger.debug("Field %s not present on the edit form", field.key)
            continue
        text = (
            located.element.inner_text() if field.rich else located.element.input_value()
        )
        out[field.key] = (text or "").strip()
    return out


def require_fields(page: PageLike) -> None:
    """Raise when any expected field is missing from the edit form."""
    missing = absent_fields(page)
    if missing:
        raise MissingGobFieldError(missing[0])


def plan_writes(current: dict[str, str], desired: dict[str, str]) -> list[FieldWrite]:
    """Only real changes, and never an empty text over something the portal holds.

    Raises ``MissingGobFieldError`` when an expected field key is absent from
    ``current`` (the portal no longer exposes it).
    """
    for field in FIELDS:
        if field.key not in current:
            raise MissingGobFieldError(field)
    writes: list[FieldWrite] = []
    for field in FIELDS:
        new = (desired.get(field.key) or "").strip()
        old = current[field.key].strip()
        if not new or _same_text(new, old):
            continue
        writes.append(FieldWrite(field=field, current=old, new=new))
    return writes


def apply_writes(page: PageLike, writes: list[FieldWrite]) -> list[FieldWrite]:
    """Set each field, then save once. Refuses to save when a write cannot sync."""
    require_fields(page)
    done: list[FieldWrite] = []
    for write in writes:
        located = locate_field(page, write.field)
        if located is None:
            raise MissingGobFieldError(write.field)
        if write.field.rich:
            _write_rich(page, located, write.new)
            # Lexxy must push text into the hidden input the form submits; Trix
            # does that inside editor.loadHTML, so the check is Lexxy-only (#264).
            if not located.is_trix:
                _assert_hidden_synced(page, write.field)
        else:
            located.element.fill(write.new)
        done.append(write)
    if done:
        page.click(SAVE_BUTTON)
        page.wait_for_timeout(2500)
    return done


def set_country(page: PageLike, value: str) -> None:
    """Set «¿Dónde vives?» on the hidden Chosen ``select`` without needing visibility."""
    select = page.query_selector(COUNTRY_SELECT)
    if select is None:
        msg = "campo no encontrado: ¿Dónde vives? (¿cambió el portal?)"
        raise RuntimeError(msg)
    select.evaluate(
        """(node, value) => {
            node.value = value;
            node.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) {
                window.jQuery(node).trigger('change').trigger('chosen:updated');
            }
        }""",
        value,
    )


def desired_from_fields(headline: str, professional: str, academic: str) -> dict[str, str]:
    """Map the permanent profile blocks onto the portal's Spanish fields."""
    return {
        "description_es": headline.strip(),
        "professional_es": professional.strip(),
        "academic_background_es": academic.strip(),
    }


def _write_rich(page: PageLike, located: LocatedField, text: str) -> None:
    if located.is_trix:
        located.element.evaluate(
            "(node, html) => node.editor.loadHTML(html)", _as_html(text)
        )
        return
    _write_lexxy(page, located.element, text)


def _write_lexxy(page: PageLike, element: ElementLike, text: str) -> None:
    """Focus the contenteditable, clear it, type paragraphs with Enter between."""
    element.click()
    element.evaluate(
        """(node) => {
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(node);
            sel.removeAllRanges();
            sel.addRange(range);
        }"""
    )
    page.keyboard.press("Backspace")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for index, paragraph in enumerate(paragraphs):
        page.keyboard.insert_text(paragraph)
        if index < len(paragraphs) - 1:
            page.keyboard.press("Enter")


def _assert_hidden_synced(page: PageLike, field: GobField) -> None:
    if not field.hidden_selector:
        return
    hidden = page.query_selector(field.hidden_selector)
    value = ""
    if hidden is not None:
        try:
            value = (hidden.input_value() or "").strip()
        except Exception:  # noqa: BLE001 — fake nodes may only expose evaluate
            raw = hidden.evaluate("(node) => node.value || ''")
            value = str(raw or "").strip()
    if not value:
        raise HiddenSyncError(field)


def _as_html(text: str) -> str:
    """Trix stores HTML: keep paragraph breaks, escape everything else."""
    paragraphs = [escape(p.strip()) for p in text.split("\n\n") if p.strip()]
    return "".join(f"<div>{p}</div>" for p in paragraphs)


def _same_text(left: str, right: str) -> bool:
    return " ".join(left.split()) == " ".join(right.split())
