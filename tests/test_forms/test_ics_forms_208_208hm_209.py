"""Tests for ICS Form 208, 208HM, and 209 YAML definitions."""
from __future__ import annotations
from pathlib import Path

import pytest

from open_packet.forms.loader import load_form, discover_forms
from open_packet.forms.validator import validate_field, validate_form

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORMS_DIR = _REPO_ROOT / "forms" / "ICS USA Forms"
_ICS208_YAML = _FORMS_DIR / "ics208_safety_message.yaml"
_ICS208HM_YAML = _FORMS_DIR / "ics208hm_site_safety_control_plan.yaml"
_ICS209_YAML = _FORMS_DIR / "ics209_incident_status_summary.yaml"


# ---------------------------------------------------------------------------
# YAML files exist
# ---------------------------------------------------------------------------

def test_ics208_yaml_present():
    assert _ICS208_YAML.exists(), f"ICS 208 YAML not found at {_ICS208_YAML}"


def test_ics208hm_yaml_present():
    assert _ICS208HM_YAML.exists(), f"ICS 208HM YAML not found at {_ICS208HM_YAML}"


def test_ics209_yaml_present():
    assert _ICS209_YAML.exists(), f"ICS 209 YAML not found at {_ICS209_YAML}"


# ---------------------------------------------------------------------------
# ICS 208 Safety Message/Plan
# ---------------------------------------------------------------------------

def test_ics208_loads():
    form = load_form(_ICS208_YAML)
    assert form.name == "ICS 208 Safety Message"
    assert form.category == "ICS USA Forms"


def test_ics208_field_count():
    form = load_form(_ICS208_YAML)
    assert len(form.fields) == 10


def test_ics208_required_fields():
    form = load_form(_ICS208_YAML)
    required = {f.name for f in form.fields if f.required}
    assert "IncidentName" in required
    assert "DateTimeFrom" in required
    assert "DateTimeTo" in required
    assert "SafetyMessage" in required
    assert "SiteSafetyPlanRequired" in required
    assert "SafetyOfficerName" in required
    assert "PreparedDateTime" in required


def test_ics208_site_safety_plan_choices():
    form = load_form(_ICS208_YAML)
    field = next(f for f in form.fields if f.name == "SiteSafetyPlanRequired")
    assert set(field.choices) == {"Yes", "No"}


def test_ics208_subject_template_references_incident_name():
    form = load_form(_ICS208_YAML)
    assert "IncidentName" in form.subject_template


def test_ics208_body_template_references_safety_message():
    form = load_form(_ICS208_YAML)
    assert "SafetyMessage" in form.body_template


def test_ics208_safety_message_is_textarea():
    form = load_form(_ICS208_YAML)
    field = next(f for f in form.fields if f.name == "SafetyMessage")
    assert field.type == "textarea"


def test_ics208_required_field_validation_fails_empty():
    form = load_form(_ICS208_YAML)
    inc_name_field = next(f for f in form.fields if f.name == "IncidentName")
    errors = validate_field(inc_name_field, "")
    assert errors


def test_ics208_valid_site_safety_plan_choice():
    form = load_form(_ICS208_YAML)
    field = next(f for f in form.fields if f.name == "SiteSafetyPlanRequired")
    assert validate_field(field, "Yes") == []
    assert validate_field(field, "No") == []


def test_ics208_invalid_site_safety_plan_choice():
    form = load_form(_ICS208_YAML)
    field = next(f for f in form.fields if f.name == "SiteSafetyPlanRequired")
    errors = validate_field(field, "Maybe")
    assert errors


# ---------------------------------------------------------------------------
# ICS 208HM Site Safety and Control Plan
# ---------------------------------------------------------------------------

def test_ics208hm_loads():
    form = load_form(_ICS208HM_YAML)
    assert form.name == "ICS 208HM Site Safety and Control Plan"
    assert form.category == "ICS USA Forms"


def test_ics208hm_field_count():
    form = load_form(_ICS208HM_YAML)
    assert len(form.fields) == 24


def test_ics208hm_required_fields():
    form = load_form(_ICS208HM_YAML)
    required = {f.name for f in form.fields if f.required}
    assert "IncidentName" in required
    assert "DateTimeFrom" in required
    assert "DateTimeTo" in required
    assert "SiteMapAttached" in required
    assert "SceneDescription" in required
    assert "EntryLeader" in required
    assert "SiteSafetyOfficer" in required
    assert "ApprovedByName" in required
    assert "ApprovedDateTime" in required


def test_ics208hm_site_map_attached_choices():
    form = load_form(_ICS208HM_YAML)
    field = next(f for f in form.fields if f.name == "SiteMapAttached")
    assert set(field.choices) == {"Yes", "No"}


def test_ics208hm_hazmat_fields_present():
    form = load_form(_ICS208HM_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 4):
        assert f"HazMatName{i}" in field_names
        assert f"HazMatUN{i}" in field_names
        assert f"HazMatClass{i}" in field_names


def test_ics208hm_scene_description_is_textarea():
    form = load_form(_ICS208HM_YAML)
    field = next(f for f in form.fields if f.name == "SceneDescription")
    assert field.type == "textarea"


def test_ics208hm_decon_procedures_is_textarea():
    form = load_form(_ICS208HM_YAML)
    field = next(f for f in form.fields if f.name == "DeconProcedures")
    assert field.type == "textarea"


def test_ics208hm_subject_template_references_incident_name():
    form = load_form(_ICS208HM_YAML)
    assert "IncidentName" in form.subject_template


def test_ics208hm_body_template_references_work_zones():
    form = load_form(_ICS208HM_YAML)
    assert "ExclusionZoneBoundary" in form.body_template


# ---------------------------------------------------------------------------
# ICS 209 Incident Status Summary
# ---------------------------------------------------------------------------

def test_ics209_loads():
    form = load_form(_ICS209_YAML)
    assert form.name == "ICS 209 Incident Status Summary"
    assert form.category == "ICS USA Forms"


def test_ics209_field_count():
    form = load_form(_ICS209_YAML)
    assert len(form.fields) == 30


def test_ics209_required_fields():
    form = load_form(_ICS209_YAML)
    required = {f.name for f in form.fields if f.required}
    assert "ReportVersion" in required
    assert "IncidentName" in required
    assert "ReportDateTime" in required
    assert "IncidentCommander" in required
    assert "IncidentStartDateTime" in required
    assert "IncidentLocation" in required
    assert "State" in required
    assert "CurrentSituation" in required
    assert "PreparedBy" in required
    assert "PreparedDateTime" in required


def test_ics209_report_version_choices():
    form = load_form(_ICS209_YAML)
    field = next(f for f in form.fields if f.name == "ReportVersion")
    assert set(field.choices) == {"Initial", "Update", "Final"}


def test_ics209_current_situation_is_textarea():
    form = load_form(_ICS209_YAML)
    field = next(f for f in form.fields if f.name == "CurrentSituation")
    assert field.type == "textarea"


def test_ics209_projected_activity_is_textarea():
    form = load_form(_ICS209_YAML)
    field = next(f for f in form.fields if f.name == "ProjectedActivity")
    assert field.type == "textarea"


def test_ics209_remarks_is_textarea():
    form = load_form(_ICS209_YAML)
    field = next(f for f in form.fields if f.name == "Remarks")
    assert field.type == "textarea"


def test_ics209_subject_template_references_incident_name():
    form = load_form(_ICS209_YAML)
    assert "IncidentName" in form.subject_template


def test_ics209_valid_report_version():
    form = load_form(_ICS209_YAML)
    field = next(f for f in form.fields if f.name == "ReportVersion")
    for version in ("Initial", "Update", "Final"):
        assert validate_field(field, version) == []


def test_ics209_invalid_report_version():
    form = load_form(_ICS209_YAML)
    field = next(f for f in form.fields if f.name == "ReportVersion")
    errors = validate_field(field, "Draft")
    assert errors


def test_ics209_resource_fields_present():
    form = load_form(_ICS209_YAML)
    field_names = {f.name for f in form.fields}
    assert "Personnel" in field_names
    assert "Aircraft" in field_names
    assert "Engines" in field_names
    assert "HeavyEquipment" in field_names
    assert "WaterTenders" in field_names


# ---------------------------------------------------------------------------
# discover_forms picks up all three new forms
# ---------------------------------------------------------------------------

def test_discover_forms_includes_ics208():
    forms = discover_forms(_REPO_ROOT / "forms")
    names = {f.name for f in forms}
    assert "ICS 208 Safety Message" in names


def test_discover_forms_includes_ics208hm():
    forms = discover_forms(_REPO_ROOT / "forms")
    names = {f.name for f in forms}
    assert "ICS 208HM Site Safety and Control Plan" in names


def test_discover_forms_includes_ics209():
    forms = discover_forms(_REPO_ROOT / "forms")
    names = {f.name for f in forms}
    assert "ICS 209 Incident Status Summary" in names
