"""Skill groups print in the profile's own order, labelled in the CV's language."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jobbot.cv.renderer import CvStyle, render_cv_ats, render_cv_tex
from jobbot.models.candidate import Candidate
from tests.fixtures.profile import nurse_profile_dict, sample_profile_dict


def _grouped_profile() -> dict[str, Any]:
    data = sample_profile_dict()
    data["skills"] = {
        "programming": ["Python", "SQL"],
        "machine_learning": ["XGBoost"],
        "cloud": ["GCP"],
        "statistics": ["Causal Inference"],
        "visualization": ["Power BI", "ggplot2"],
        "engineering": ["MLOps"],
    }
    return data


def _moderncv_labels(tex: str) -> list[str]:
    section = tex.split(r"\section{Habilidades}", 1)[1].split(r"\section", 1)[0]
    return re.findall(r"\\cvitem\{([^}]*)\}", section)


def test_moderncv_labels_known_groups_in_spanish(project_root: Path) -> None:
    candidate = Candidate.model_validate(_grouped_profile())
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)

    assert _moderncv_labels(tex) == [
        "Programación",
        "Machine Learning",
        "Cloud",
        "Estadística",
        "Herramientas de visualización",
        "Ingeniería",
    ]


def test_unknown_group_keys_fall_through_title_cased(project_root: Path) -> None:
    """The label table only adds translations: any other key prints as before."""
    data = nurse_profile_dict()
    data["skills"] = {"cuidados_criticos": ["Ventilación mecánica"]}
    candidate = Candidate.model_validate(data)
    templates = project_root / "templates"

    assert _moderncv_labels(render_cv_tex(candidate, templates)) == ["Cuidados Criticos"]
    assert "Cuidados Criticos: Ventilación mecánica" in render_cv_ats(candidate, templates)


def test_english_outputs_keep_english_labels(project_root: Path) -> None:
    candidate = Candidate.model_validate(_grouped_profile())
    templates = project_root / "templates"
    plain = render_cv_tex(candidate, templates, style=CvStyle.PLAIN)
    ats = render_cv_ats(candidate, templates).splitlines()

    assert r"\textbf{Programming}: Python, SQL" in plain
    assert r"\textbf{Visualization}: Power BI, ggplot2" in plain
    assert "Programación" not in plain
    assert "Statistics: Causal Inference" in ats
    assert "Visualization: Power BI, ggplot2" in ats


def test_groups_print_in_profile_order(project_root: Path) -> None:
    """A group the candidate added is not pushed behind the built-in ones."""
    data = sample_profile_dict()
    data["skills"] = {
        "visualization": ["Power BI"],
        "statistics": ["Causal Inference"],
        "programming": ["Python"],
    }
    candidate = Candidate.model_validate(data)
    templates = project_root / "templates"

    assert list(candidate.skills.as_dict()) == ["visualization", "statistics", "programming"]
    assert candidate.skills.all_skills() == ["Power BI", "Causal Inference", "Python"]
    assert _moderncv_labels(render_cv_tex(candidate, templates)) == [
        "Herramientas de visualización",
        "Estadística",
        "Programación",
    ]
    ats = render_cv_ats(candidate, templates)
    assert ats.index("Visualization:") < ats.index("Statistics:") < ats.index("Programming:")


def test_profile_order_survives_a_model_copy() -> None:
    data = sample_profile_dict()
    data["skills"] = {"visualization": ["Power BI"], "programming": ["Python"]}
    candidate = Candidate.model_validate(data)

    assert list(candidate.model_copy(deep=True).skills.as_dict()) == [
        "visualization",
        "programming",
    ]
