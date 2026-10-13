"""The base CV renders every fact of profile.yaml, in every style and in the ATS text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobbot.cv import build as build_module
from jobbot.cv.build import BuildTarget, build_cv
from jobbot.cv.latex import escape_latex
from jobbot.cv.renderer import CvStyle, render_cv_ats, render_cv_tex
from jobbot.models.candidate import Candidate
from jobbot.models.experience import format_metric
from jobbot.resources import iter_template_names, resource_text
from tests.fixtures.profile import sample_profile_dict


def _full_profile() -> dict[str, Any]:
    """Every optional section populated, so a dropped field has nowhere to hide."""
    data = sample_profile_dict()
    data["personal"]["orcid"] = "0000-0002-1825-0097"
    data["specialties"] = ["Pronóstico de Demanda", "Diseño Experimental"]
    data["experience"].append(
        {
            "id": "retail-co",
            "company": "Retail Co",
            "title": "Data Scientist",
            "location": "Santiago, Chile",
            "start_date": "2019-01",
            "end_date": "2022-03",
            "current": False,
            "description": "Forecasting y pricing para retail omnicanal.",
            "achievements": [
                {
                    "id": "retail-forecast",
                    "text": "Pronóstico semanal de demanda por tienda.",
                    "tags": ["forecasting"],
                    "metrics": {"stores": 120},
                },
                {
                    "id": "retail-pricing",
                    "text": "Motor de precios con elasticidades por categoría.",
                    "tags": [],
                    "metrics": {},
                },
            ],
        }
    )
    data["education"][0]["details"] = "Tesis en inferencia causal."
    data["education"].append(
        {
            "id": "uni-ing",
            "institution": "Universidad del Litoral",
            "degree": "Ingeniería Matemática",
            "start_date": "2010-03",
            "end_date": "2016-12",
        }
    )
    data["publications"][0]["authors"] = ["Ejemplo, A.", "Rivas, B.", "Soto, C."]
    data["publications"].append(
        {
            "id": "pub-2",
            "title": "Demand under stockouts",
            "journal": "Revista de Ejemplo",
            "year": 2023,
            "doi": "10.1000/xyz123",
            "authors": ["Rivas, B.", "Ejemplo, A."],
        }
    )
    data["projects"] = [
        {
            "id": "huerto",
            "name": "Huerto Comunitario",
            "description": "Coordinación de un huerto vecinal.",
            "url": "https://example.org/huerto",
            "tags": ["Compostaje", "Riego"],
        }
    ]
    return data


def _facts(candidate: Candidate) -> list[str]:
    facts: list[str] = [candidate.personal.headline, candidate.summary or ""]
    facts += candidate.specialties
    for exp in candidate.experience:
        facts += [exp.title, exp.company, exp.location or "", exp.description or ""]
        for ach in exp.achievements:
            facts.append(ach.text)
            facts += [format_metric(k, v) for k, v in ach.metrics.items()]
    for edu in candidate.education:
        facts += [edu.degree, edu.institution, edu.details or ""]
    facts += candidate.skills.all_skills()
    for pub in candidate.publications:
        facts += [pub.title, pub.journal or "", pub.status or "", pub.doi or "", *pub.authors]
    for project in candidate.projects:
        facts += [project.name, project.description, *project.tags]
    return [fact for fact in facts if fact]


@pytest.mark.parametrize("style", list(CvStyle))
def test_base_tex_renders_every_profile_fact(project_root: Path, style: CvStyle) -> None:
    candidate = Candidate.model_validate(_full_profile())
    tex = render_cv_tex(candidate, project_root / "templates", style=style)

    missing = [fact for fact in _facts(candidate) if escape_latex(fact) not in tex]
    assert missing == []


def test_base_ats_renders_every_profile_fact(project_root: Path) -> None:
    candidate = Candidate.model_validate(_full_profile())
    ats = render_cv_ats(candidate, project_root / "templates")

    missing = [fact for fact in _facts(candidate) if fact not in ats]
    assert missing == []


def _no_xelatex(tex_path: Path, work_dir: Path) -> Path:
    raise RuntimeError("XeLaTeX is required")


def test_base_pdf_build_rewrites_ats_text(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A base `cv build` must not leave an ATS text from an older profile beside the PDF."""
    output = tmp_path / "output"
    stale = output / "base" / "cv_ats.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old profile\n", encoding="utf-8")

    def fake_pdf(tex_path: Path, work_dir: Path) -> Path:
        pdf = work_dir / "cv.pdf"
        pdf.write_bytes(b"%PDF-1.5\n")
        return pdf

    monkeypatch.setattr(build_module, "_compile_xelatex", fake_pdf)
    candidate = Candidate.model_validate(_full_profile())
    written = build_cv(candidate, project_root / "templates", output, target=BuildTarget.CV)

    assert stale in written
    text = stale.read_text(encoding="utf-8")
    assert "old profile" not in text
    assert "Rivas, B." in text


def test_base_ats_text_is_written_even_without_xelatex(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ATS text needs no TeX: a missing XeLaTeX must not leave it stale."""
    monkeypatch.setattr(build_module, "_compile_xelatex", _no_xelatex)
    candidate = Candidate.model_validate(_full_profile())
    output = tmp_path / "output"

    with pytest.raises(RuntimeError):
        build_cv(candidate, project_root / "templates", output, target=BuildTarget.CV)

    assert "Huerto Comunitario" in (output / "base" / "cv_ats.txt").read_text(encoding="utf-8")


def test_packaged_templates_match_the_checkout(project_root: Path) -> None:
    """`jobbot init` copies the packaged templates: a stale copy renders an incomplete CV."""
    stale = [
        name
        for name in iter_template_names()
        if name.endswith(".j2")
        and (project_root / "templates" / name).is_file()
        and resource_text(f"templates/{name}")
        != (project_root / "templates" / name).read_text(encoding="utf-8")
    ]
    assert stale == []
