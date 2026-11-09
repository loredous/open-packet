"""Tests for ICS Form 220, 225, and 230CG YAML definitions."""
from __future__ import annotations
from pathlib import Path

import pytest

from open_packet.forms.loader import load_form, discover_forms
from open_packet.forms.validator import validate_field, validate_form

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORMS_DIR = _REPO_ROOT / "forms" / "ICS USA Forms"
_ICS220_YAML = _FORMS_DIR / "ics220_air_operations_summary.yaml"
_ICS225_YAML = _FORMS_DIR / "ics225_incident_personnel_performance_rating.yaml"
_ICS230CG_YAML = _FORMS_DIR / "ics230cg_daily_meeting_schedule.yaml"


# ---------------------------------------------------------------------------
# YAML files exist
# ---------------------------------------------------------------------------

def test_ics220_yaml_present():
    assert _ICS220_YAML.exists(), f"ICS 220 YAML not found at {_ICS220_YAML}"


def test_ics225_yaml_present():
    assert _ICS225_YAML.exists(), f"ICS 225 YAML not found at {_ICS225_YAML}"


def test_ics230cg_yaml_present():
    assert _ICS230CG_YAML.exists(), f"ICS 230CG YAML not found at {_ICS230CG_YAML}"


# ---------------------------------------------------------------------------
# ICS 220 Air Operations Summary
# ---------------------------------------------------------------------------

def test_ics220_loads():
    form = load_form(_ICS220_YAML)
    assert form.name == "ICS 220 Air Operations Summary"
    assert form.category == "ICS USA Forms"


def test_ics220_field_count():
    form = load_form(_ICS220_YAML)
    assert len(form.fields) == 91


def test_ics220_required_fields():
    form = load_form(_ICS220_YAML)
    required = {f.name for f in form.fields if f.required}
    assert "IncidentName" in required
    assert "DateFrom" in required
    assert "DateTo" in required
    assert "TimeFrom" in required
    assert "TimeTo" in required
    assert "AirOpsBranchDirector" in required
    assert "PreparedBy" in required
    assert "PrepPosition" in required
    assert "PrepDateTime" in required


def test_ics220_helicopter_fields_present():
    form = load_form(_ICS220_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 6):
        assert f"Helo{i}Name" in field_names
        assert f"Helo{i}Type" in field_names
        assert f"Helo{i}Agency" in field_names
        assert f"Helo{i}Freq" in field_names
        assert f"Helo{i}Capacity" in field_names
        assert f"Helo{i}Assignment" in field_names
        assert f"Helo{i}ETA" in field_names
        assert f"Helo{i}ETD" in field_names


def test_ics220_fixed_wing_fields_present():
    form = load_form(_ICS220_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 6):
        assert f"FW{i}Name" in field_names
        assert f"FW{i}Type" in field_names
        assert f"FW{i}Agency" in field_names
        assert f"FW{i}Freq" in field_names
        assert f"FW{i}Capacity" in field_names
        assert f"FW{i}Assignment" in field_names
        assert f"FW{i}ETA" in field_names
        assert f"FW{i}ETD" in field_names


def test_ics220_remarks_is_textarea():
    form = load_form(_ICS220_YAML)
    field = next(f for f in form.fields if f.name == "Remarks")
    assert field.type == "textarea"


def test_ics220_subject_template_references_incident_name():
    form = load_form(_ICS220_YAML)
    assert "IncidentName" in form.subject_template


def test_ics220_body_template_references_air_ops_director():
    form = load_form(_ICS220_YAML)
    assert "AirOpsBranchDirector" in form.body_template


def test_ics220_required_field_validation_fails_empty():
    form = load_form(_ICS220_YAML)
    field = next(f for f in form.fields if f.name == "IncidentName")
    errors = validate_field(field, "")
    assert errors


def test_ics220_helicopter_fields_not_required():
    form = load_form(_ICS220_YAML)
    helo_fields = [f for f in form.fields if f.name.startswith("Helo")]
    assert all(not f.required for f in helo_fields)


def test_ics220_fixed_wing_fields_not_required():
    form = load_form(_ICS220_YAML)
    fw_fields = [f for f in form.fields if f.name.startswith("FW")]
    assert all(not f.required for f in fw_fields)


# ---------------------------------------------------------------------------
# ICS 225 Incident Personnel Performance Rating
# ---------------------------------------------------------------------------

def test_ics225_loads():
    form = load_form(_ICS225_YAML)
    assert form.name == "ICS 225 Incident Personnel Performance Rating"
    assert form.category == "ICS USA Forms"


def test_ics225_field_count():
    form = load_form(_ICS225_YAML)
    assert len(form.fields) == 27


def test_ics225_required_fields():
    form = load_form(_ICS225_YAML)
    required = {f.name for f in form.fields if f.required}
    assert "IncidentName" in required
    assert "EvaluationDate" in required
    assert "EvaluateeName" in required
    assert "HomeUnit" in required
    assert "ICSPosition" in required
    assert "RatingKnowledgeOfJob" in required
    assert "RatingCompletedAssignments" in required
    assert "RatingWorkedWithinICS" in required
    assert "RatingCommunicatedSupervisor" in required
    assert "RatingWorkedSafely" in required
    assert "RatingProfessionalAttitude" in required
    assert "OverallRating" in required
    assert "RecommendIncreased" in required
    assert "Strengths" in required
    assert "AreasForImprovement" in required
    assert "EvaluatorName" in required
    assert "EvaluatorPosition" in required
    assert "EvaluatorDateTime" in required


def test_ics225_rating_choices():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "RatingKnowledgeOfJob")
    assert set(field.choices) == {"1", "2", "3", "4", "N/A"}


def test_ics225_overall_rating_choices():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "OverallRating")
    assert set(field.choices) == {"1", "2", "3", "4"}


def test_ics225_recommend_increased_choices():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "RecommendIncreased")
    assert set(field.choices) == {"Yes", "Yes with Reservation", "No"}


def test_ics225_strengths_is_textarea():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "Strengths")
    assert field.type == "textarea"


def test_ics225_areas_for_improvement_is_textarea():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "AreasForImprovement")
    assert field.type == "textarea"


def test_ics225_subject_template_references_evaluatee():
    form = load_form(_ICS225_YAML)
    assert "EvaluateeName" in form.subject_template


def test_ics225_valid_rating_choice():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "OverallRating")
    for val in ("1", "2", "3", "4"):
        assert validate_field(field, val) == []


def test_ics225_invalid_rating_choice():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "OverallRating")
    errors = validate_field(field, "5")
    assert errors


def test_ics225_valid_recommend_choice():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "RecommendIncreased")
    for val in ("Yes", "Yes with Reservation", "No"):
        assert validate_field(field, val) == []


def test_ics225_invalid_recommend_choice():
    form = load_form(_ICS225_YAML)
    field = next(f for f in form.fields if f.name == "RecommendIncreased")
    errors = validate_field(field, "Maybe")
    assert errors


# ---------------------------------------------------------------------------
# ICS 230CG Daily Meeting Schedule
# ---------------------------------------------------------------------------

def test_ics230cg_loads():
    form = load_form(_ICS230CG_YAML)
    assert form.name == "ICS 230CG Daily Meeting Schedule"
    assert form.category == "ICS USA Forms"


def test_ics230cg_field_count():
    form = load_form(_ICS230CG_YAML)
    assert len(form.fields) == 40


def test_ics230cg_required_fields():
    form = load_form(_ICS230CG_YAML)
    required = {f.name for f in form.fields if f.required}
    assert "IncidentName" in required
    assert "DateFrom" in required
    assert "DateTo" in required
    assert "TimeFrom" in required
    assert "TimeTo" in required
    assert "PreparedBy" in required
    assert "PrepPosition" in required
    assert "PrepDateTime" in required


def test_ics230cg_meeting_fields_present():
    form = load_form(_ICS230CG_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 9):
        assert f"Meeting{i}Time" in field_names
        assert f"Meeting{i}Name" in field_names
        assert f"Meeting{i}Location" in field_names
        assert f"Meeting{i}Attendees" in field_names


def test_ics230cg_meeting_fields_not_required():
    form = load_form(_ICS230CG_YAML)
    meeting_fields = [f for f in form.fields if f.name.startswith("Meeting")]
    assert all(not f.required for f in meeting_fields)


def test_ics230cg_subject_template_references_incident_name():
    form = load_form(_ICS230CG_YAML)
    assert "IncidentName" in form.subject_template


def test_ics230cg_body_template_references_meetings():
    form = load_form(_ICS230CG_YAML)
    assert "Meeting1Name" in form.body_template


def test_ics230cg_required_field_validation_fails_empty():
    form = load_form(_ICS230CG_YAML)
    field = next(f for f in form.fields if f.name == "IncidentName")
    errors = validate_field(field, "")
    assert errors


# ---------------------------------------------------------------------------
# discover_forms picks up all three new forms
# ---------------------------------------------------------------------------

def test_discover_forms_includes_ics220():
    forms = discover_forms(_REPO_ROOT / "forms")
    names = {f.name for f in forms}
    assert "ICS 220 Air Operations Summary" in names


def test_discover_forms_includes_ics225():
    forms = discover_forms(_REPO_ROOT / "forms")
    names = {f.name for f in forms}
    assert "ICS 225 Incident Personnel Performance Rating" in names


def test_discover_forms_includes_ics230cg():
    forms = discover_forms(_REPO_ROOT / "forms")
    names = {f.name for f in forms}
    assert "ICS 230CG Daily Meeting Schedule" in names
