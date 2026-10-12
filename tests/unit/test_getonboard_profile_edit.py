"""Writing the permanent Get on Board profile: Trix + Lexxy, never silent skip."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

from jobbot.adapters.getonboard.profile_edit import (
    COUNTRY_SELECT,
    FIELDS,
    SAVE_BUTTON,
    FieldWrite,
    HiddenSyncError,
    MissingGobFieldError,
    apply_writes,
    desired_from_fields,
    locate_field,
    plan_writes,
    read_current,
    set_country,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "getonboard"
OLD_TEXT = "Me he dedicado a trabajos numéricos en matlab y C++."
NEW_TEXT = "Senior Data Scientist con 12 años de experiencia.\n\nStack: Python, SQL, R."


class FakeKeyboard:
    def __init__(self, target: FakeLexxy | None = None) -> None:
        self.target = target
        self.actions: list[str] = []

    def press(self, key: str) -> None:
        self.actions.append(f"press:{key}")
        if self.target is None:
            return
        if key == "Backspace":
            self.target.text = ""
            self.target.sync_hidden()
        elif key == "Enter":
            self.target.text = (self.target.text + "\n\n").lstrip()
            self.target.sync_hidden()

    def insert_text(self, text: str) -> None:
        self.actions.append(f"type:{text}")
        if self.target is not None:
            self.target.text += text
            self.target.sync_hidden()


class FakeTrix:
    """A Trix editor: text is read from the node, written through editor.loadHTML."""

    def __init__(self, text: str = "", *, hidden: FakeInput | None = None) -> None:
        self.text = text
        self.hidden = hidden
        self.loaded_html: str | None = None
        if hidden is not None and text:
            hidden.value = text

    def inner_text(self) -> str:
        return self.text

    def input_value(self) -> str:  # pragma: no cover - trix reads via inner_text
        raise AssertionError("a trix editor must not be read as an input")

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        assert "editor.loadHTML" in expression, expression
        self.loaded_html = str(arg)
        plain = BeautifulSoup(str(arg), "html.parser").get_text("\n\n")
        self.text = plain.strip()
        if self.hidden is not None:
            self.hidden.value = self.text
        return None

    def fill(self, value: str) -> None:  # pragma: no cover - would silently no-op
        raise AssertionError("fill() does not reach the Trix hidden input")

    def click(self) -> None:
        return None


class FakeLexxy:
    """Lexxy contenteditable: keyboard typing syncs a hidden input."""

    def __init__(self, text: str = "", *, hidden: FakeInput | None = None) -> None:
        self.text = text
        self.hidden = hidden
        self.focused = False
        if hidden is not None and text:
            hidden.value = text

    def inner_text(self) -> str:
        return self.text

    def input_value(self) -> str:  # pragma: no cover
        raise AssertionError("lexxy is read via inner_text")

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        if "selectNodeContents" in expression:
            return None
        raise AssertionError(f"unexpected evaluate on lexxy: {expression}")

    def fill(self, value: str) -> None:  # pragma: no cover
        raise AssertionError("fill() does not reach the Lexxy hidden input")

    def click(self) -> None:
        self.focused = True

    def sync_hidden(self) -> None:
        if self.hidden is not None:
            self.hidden.value = self.text.strip()


class FakeInput:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.events: list[str] = []

    def inner_text(self) -> str:  # pragma: no cover
        raise AssertionError("a plain input must be read with input_value()")

    def input_value(self) -> str:
        return self.value

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        if "node.value = value" in expression or "node.value = value" in expression.replace(
            " ", ""
        ):
            self.value = str(arg)
            self.events.append("change")
            return None
        if "node.value" in expression:
            return self.value
        raise AssertionError(f"unexpected evaluate on input: {expression}")

    def fill(self, value: str) -> None:
        self.value = value

    def click(self) -> None:
        return None


class FakeSelect(FakeInput):
    """Hidden Chosen select: value set via evaluate, not Playwright select_option."""


class FakeEditPage:
    def __init__(self, elements: dict[str, Any], *, keyboard: FakeKeyboard | None = None) -> None:
        self.elements = elements
        self.clicked: list[str] = []
        self.visited: list[str] = []
        self.keyboard = keyboard or FakeKeyboard()

    def goto(self, url: str, **_: Any) -> None:
        self.visited.append(url)

    def query_selector(self, selector: str) -> Any:
        return self.elements.get(selector)

    def click(self, selector: str, **_: Any) -> None:
        self.clicked.append(selector)

    def wait_for_timeout(self, _timeout: float) -> None:
        return None


class SoupElement:
    def __init__(self, tag: Any) -> None:
        self._tag = tag

    def inner_text(self) -> str:
        return self._tag.get_text(" ", strip=True)

    def input_value(self) -> str:
        return str(self._tag.get("value") or "")

    def evaluate(self, expression: str, arg: Any = None) -> Any:  # pragma: no cover
        raise AssertionError("fixture reads do not evaluate JS")

    def fill(self, value: str) -> None:  # pragma: no cover
        raise AssertionError("fixture reads do not fill")

    def click(self) -> None:  # pragma: no cover
        return None


class SoupPage:
    """Minimal PageLike over a saved Get on Board edit-form HTML fixture."""

    def __init__(self, html: str) -> None:
        self._soup = BeautifulSoup(html, "html.parser")
        self.keyboard = FakeKeyboard()

    def goto(self, url: str, **_: Any) -> None:
        return None

    def query_selector(self, selector: str) -> SoupElement | None:
        tag = self._select(selector)
        return SoupElement(tag) if tag is not None else None

    def click(self, selector: str, **_: Any) -> None:  # pragma: no cover
        return None

    def wait_for_timeout(self, _timeout: float) -> None:
        return None

    def _select(self, selector: str) -> Any:
        if selector.startswith("trix-editor#"):
            return self._soup.select_one(selector)
        if selector.startswith("#") and "[contenteditable]" in selector:
            element_id = selector.split("[", 1)[0].lstrip("#")
            tag = self._soup.find(id=element_id)
            if tag is not None and tag.has_attr("contenteditable"):
                return tag
            return None
        if selector.startswith("input[name=") or selector.startswith("select[name="):
            name = selector.split('"')[1]
            return self._soup.find(["input", "select"], attrs={"name": name})
        return self._soup.select_one(selector)


def _trix_page(
    *, description: str = "", professional: str = OLD_TEXT, academic: str = ""
) -> FakeEditPage:
    hidden_pro = FakeInput(professional)
    hidden_acad = FakeInput(academic)
    by_key = {
        "description_es": FakeInput(description),
        "professional_es": FakeTrix(professional, hidden=hidden_pro),
        "academic_background_es": FakeTrix(academic, hidden=hidden_acad),
    }
    elements: dict[str, Any] = {field.selectors[0]: by_key[field.key] for field in FIELDS}
    for field in FIELDS:
        if field.hidden_selector:
            if field.key == "professional_es":
                elements[field.hidden_selector] = hidden_pro
            else:
                elements[field.hidden_selector] = hidden_acad
    return FakeEditPage(elements)


def _lexxy_page(
    *,
    description: str = "",
    professional: str = OLD_TEXT,
    academic: str = "",
    sync_hidden: bool = True,
) -> FakeEditPage:
    hidden_pro = FakeInput(professional if sync_hidden else "")
    hidden_acad = FakeInput(academic if sync_hidden else "")
    pro = FakeLexxy(professional, hidden=hidden_pro if sync_hidden else None)
    acad = FakeLexxy(academic, hidden=hidden_acad if sync_hidden else None)
    # When sync is disabled, still expose empty hiddens that stay empty.
    if not sync_hidden:
        pro.hidden = None
        acad.hidden = None

    elements: dict[str, Any] = {
        'input[name="webpro[description_es]"]': FakeInput(description),
        "#trix-professional_es-content[contenteditable]": pro,
        "#trix-academic_background_es-content[contenteditable]": acad,
        'input[name="webpro[professional_background_es]"]': hidden_pro,
        'input[name="webpro[academic_background_es]"]': hidden_acad,
        COUNTRY_SELECT: FakeSelect("CL"),
    }
    keyboard = FakeKeyboard(target=pro)
    page = FakeEditPage(elements, keyboard=keyboard)

    def _retarget(selector: str) -> None:
        # Point keyboard at whichever Lexxy node was last clicked.
        node = elements.get(selector)
        if isinstance(node, FakeLexxy):
            keyboard.target = node

    original_query = page.query_selector

    def query_selector(selector: str) -> Any:
        node = original_query(selector)
        if isinstance(node, FakeLexxy):
            keyboard.target = node
        return node

    page.query_selector = query_selector  # type: ignore[method-assign]
    _ = _retarget
    return page


def test_plan_reports_what_the_portal_holds_today() -> None:
    page = _trix_page()
    desired = desired_from_fields(
        "Senior Data Scientist", NEW_TEXT, "Magíster en Estadística — PUC."
    )

    writes = plan_writes(read_current(page), desired)

    described = " ".join(write.describe() for write in writes)
    assert "replace Perfil profesional y experiencia laboral" in described
    assert "fill Formación académica y estudios" in described
    assert "fill Descripción profesional" in described
    assert page.clicked == [], "planning must not touch the form"


def test_unchanged_fields_are_not_rewritten() -> None:
    page = _trix_page(description="Senior Data Scientist", professional=NEW_TEXT, academic="PUC.")
    desired = desired_from_fields("Senior Data Scientist", NEW_TEXT, "PUC.")

    assert plan_writes(read_current(page), desired) == []


def test_whitespace_only_differences_are_not_a_change() -> None:
    page = _trix_page(professional="Senior   Data Scientist\n\nStack: Python.")
    desired = desired_from_fields("", "Senior Data Scientist\n\nStack: Python.", "")

    assert plan_writes(read_current(page), desired) == []


def test_an_empty_draft_never_wipes_the_portal() -> None:
    page = _trix_page(description="Algo escrito", professional=OLD_TEXT, academic="Estudios.")

    assert plan_writes(read_current(page), desired_from_fields("", "", "")) == []


def test_apply_writes_trix_as_html_and_saves_once() -> None:
    page = _trix_page()
    desired = desired_from_fields("Senior Data Scientist", NEW_TEXT, "PUC.")

    done = apply_writes(page, plan_writes(read_current(page), desired))

    assert {write.field.key for write in done} == {
        "description_es",
        "professional_es",
        "academic_background_es",
    }
    professional = page.elements[
        next(f.selectors[0] for f in FIELDS if f.key == "professional_es")
    ]
    assert professional.loaded_html is not None
    assert professional.loaded_html.count("<div>") == 2
    description = page.elements[next(f.selectors[0] for f in FIELDS if f.key == "description_es")]
    assert description.value == "Senior Data Scientist"
    assert page.clicked == [SAVE_BUTTON]


def test_nothing_to_write_means_nothing_is_saved() -> None:
    page = _trix_page(description="X", professional=OLD_TEXT, academic="Y")

    assert apply_writes(page, []) == []
    assert page.clicked == []


def test_html_in_the_draft_is_escaped_not_injected() -> None:
    page = _trix_page()
    desired = desired_from_fields("", "Trabajé con <script>alert(1)</script> y R.", "")

    apply_writes(page, plan_writes(read_current(page), desired))

    professional = page.elements[
        next(f.selectors[0] for f in FIELDS if f.key == "professional_es")
    ]
    assert professional.loaded_html is not None
    assert "<script>" not in professional.loaded_html
    assert "&lt;script&gt;" in professional.loaded_html


def test_read_current_from_lexxy_fixture() -> None:
    html = (FIXTURES / "webpros_edit_lexxy.html").read_text(encoding="utf-8")
    current = read_current(SoupPage(html))
    assert current["description_es"] == "Public health professional."
    assert current["professional_es"] == "Campo epidemiolx."
    assert current["academic_background_es"] == "FETP."


def test_read_current_from_trix_fixture_still_works() -> None:
    html = (FIXTURES / "webpros_edit_trix.html").read_text(encoding="utf-8")
    current = read_current(SoupPage(html))
    assert current["description_es"] == "Data professional."
    assert current["professional_es"] == "Experiencia previa."
    assert current["academic_background_es"] == "Magíster."


def test_missing_formation_is_an_error_and_does_not_save() -> None:
    page = _lexxy_page()
    del page.elements["#trix-academic_background_es-content[contenteditable]"]
    desired = desired_from_fields("Headline", NEW_TEXT, "FETP.")

    with pytest.raises(MissingGobFieldError, match="Formación académica y estudios"):
        plan_writes(read_current(page), desired)

    with pytest.raises(MissingGobFieldError, match="Formación académica y estudios"):
        apply_writes(
            page,
            [
                FieldWrite(
                    field=next(f for f in FIELDS if f.key == "description_es"),
                    current="",
                    new="Headline",
                )
            ],
        )
    assert page.clicked == []


def test_empty_hidden_after_lexxy_write_refuses_save() -> None:
    page = _lexxy_page(sync_hidden=False)
    # Contenteditable present, but typing must not fill the hidden (broken sync).
    page.keyboard = FakeKeyboard(target=None)
    writes = [
        FieldWrite(
            field=next(f for f in FIELDS if f.key == "professional_es"),
            current=OLD_TEXT,
            new="Un párrafo.",
        )
    ]
    # require_fields needs all three present — academic also won't sync.
    with pytest.raises(HiddenSyncError, match="no sincronizó"):
        apply_writes(page, writes)
    assert page.clicked == []


def test_lexxy_write_types_paragraphs_and_saves() -> None:
    page = _lexxy_page(professional="viejo", academic="viejo")
    desired = desired_from_fields("Headline", NEW_TEXT, "FETP completo.")

    done = apply_writes(page, plan_writes(read_current(page), desired))

    assert {w.field.key for w in done} == {
        "description_es",
        "professional_es",
        "academic_background_es",
    }
    pro_hidden = page.elements['input[name="webpro[professional_background_es]"]']
    assert "Senior Data Scientist" in pro_hidden.value
    assert page.clicked == [SAVE_BUTTON]
    assert any(a.startswith("type:") for a in page.keyboard.actions)


def test_set_country_updates_hidden_select_without_visibility() -> None:
    select = FakeSelect("CL")
    page = FakeEditPage({COUNTRY_SELECT: select})
    set_country(page, "PE")
    assert select.value == "PE"
    assert "change" in select.events


def test_locate_prefers_trix_when_both_exist() -> None:
    page = _trix_page()
    # Also plant a Lexxy node; Trix selector is first.
    page.elements["#trix-professional_es-content[contenteditable]"] = FakeLexxy("lexxy")
    located = locate_field(page, next(f for f in FIELDS if f.key == "professional_es"))
    assert located is not None
    assert located.is_trix
