"""Tests for ICS Form definitions: 205A (Communications List),
206 (Medical Plan), and 207 (Incident Organization Chart)."""
from __future__ import annotations
from pathlib import Path

import pytest

from open_packet.forms.loader import load_form

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ICS_DIR = _REPO_ROOT / "forms" / "ICS USA Forms"
_ICS205A_YAML = _ICS_DIR / "ics205a_communications_list.yaml"
_ICS206_YAML = _ICS_DIR / "ics206_medical_plan.yaml"
_ICS207_YAML = _ICS_DIR / "ics207_incident_organization_chart.yaml"


# ---------------------------------------------------------------------------
# Hard-fail if any YAML is missing
# ---------------------------------------------------------------------------

def test_ics205a_yaml_present():
    assert _ICS205A_YAML.exists(), (
        f"ICS 205A YAML not found at {_ICS205A_YAML}."
    )


def test_ics206_yaml_present():
    assert _ICS206_YAML.exists(), (
        f"ICS 206 YAML not found at {_ICS206_YAML}."
    )


def test_ics207_yaml_present():
    assert _ICS207_YAML.exists(), (
        f"ICS 207 YAML not found at {_ICS207_YAML}."
    )


# ---------------------------------------------------------------------------
# ICS 205A – Communications List
# ---------------------------------------------------------------------------

def test_ics205a_loads():
    form = load_form(_ICS205A_YAML)
    assert form.name == "ICS 205A Communications List"
    assert form.category == "ICS USA Forms"


def test_ics205a_has_required_fields():
    form = load_form(_ICS205A_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "Incident_Name", "DateTimePrepared",
        "DateFrom", "TimeFrom", "DateTo", "TimeTo",
        "PreparedName", "PreparedDateTime",
    }
    assert required <= field_names


def test_ics205a_has_entry_rows():
    form = load_form(_ICS205A_YAML)
    field_names = {f.name for f in form.fields}
    # At least 8 rows of contact info
    for i in range(1, 9):
        assert f"Name{i}" in field_names, f"Name{i} missing"
        assert f"Position{i}" in field_names, f"Position{i} missing"
        assert f"CellPhone{i}" in field_names, f"CellPhone{i} missing"
        assert f"Email{i}" in field_names, f"Email{i} missing"


def test_ics205a_incident_name_required():
    form = load_form(_ICS205A_YAML)
    incident = next(f for f in form.fields if f.name == "Incident_Name")
    assert incident.required is True


def test_ics205a_subject_template_contains_incident_name():
    form = load_form(_ICS205A_YAML)
    assert "Incident_Name" in form.subject_template


def test_ics205a_body_template_contains_key_sections():
    form = load_form(_ICS205A_YAML)
    assert "ICS 205A" in form.body_template
    assert "COMMUNICATIONS LIST" in form.body_template


# ---------------------------------------------------------------------------
# ICS 206 – Medical Plan
# ---------------------------------------------------------------------------

def test_ics206_loads():
    form = load_form(_ICS206_YAML)
    assert form.name == "ICS 206 Medical Plan"
    assert form.category == "ICS USA Forms"


def test_ics206_has_required_fields():
    form = load_form(_ICS206_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "Incident_Name", "DateTimePrepared",
        "DateFrom", "TimeFrom", "DateTo", "TimeTo",
        "PreparedName", "PreparedDateTime",
    }
    assert required <= field_names


def test_ics206_has_aid_station_fields():
    form = load_form(_ICS206_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 4):
        assert f"AidStation{i}" in field_names, f"AidStation{i} missing"
        assert f"AidLocation{i}" in field_names, f"AidLocation{i} missing"
        assert f"AidPhone{i}" in field_names, f"AidPhone{i} missing"


def test_ics206_has_transportation_fields():
    form = load_form(_ICS206_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 3):
        assert f"Ambulance{i}" in field_names, f"Ambulance{i} missing"
        assert f"AmbulancePhone{i}" in field_names, f"AmbulancePhone{i} missing"


def test_ics206_has_hospital_fields():
    form = load_form(_ICS206_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 3):
        assert f"Hospital{i}" in field_names, f"Hospital{i} missing"
        assert f"HospitalPhone{i}" in field_names, f"HospitalPhone{i} missing"
        assert f"HospitalTrauma{i}" in field_names, f"HospitalTrauma{i} missing"


def test_ics206_has_special_procedures_textarea():
    form = load_form(_ICS206_YAML)
    sp = next(f for f in form.fields if f.name == "SpecialProcedures")
    assert sp.type == "textarea"


def test_ics206_has_safety_officer_approval():
    form = load_form(_ICS206_YAML)
    field_names = {f.name for f in form.fields}
    assert "ApprovedName" in field_names
    assert "ApprovedDateTime" in field_names


def test_ics206_incident_name_required():
    form = load_form(_ICS206_YAML)
    incident = next(f for f in form.fields if f.name == "Incident_Name")
    assert incident.required is True


def test_ics206_subject_template_contains_incident_name():
    form = load_form(_ICS206_YAML)
    assert "Incident_Name" in form.subject_template


def test_ics206_body_template_contains_key_sections():
    form = load_form(_ICS206_YAML)
    assert "ICS 206" in form.body_template
    assert "MEDICAL PLAN" in form.body_template
    assert "TRANSPORTATION" in form.body_template
    assert "HOSPITALS" in form.body_template


# ---------------------------------------------------------------------------
# ICS 207 – Incident Organization Chart
# ---------------------------------------------------------------------------

def test_ics207_loads():
    form = load_form(_ICS207_YAML)
    assert form.name == "ICS 207 Incident Organization Chart"
    assert form.category == "ICS USA Forms"


def test_ics207_has_required_fields():
    form = load_form(_ICS207_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "Incident_Name", "DateTimePrepared",
        "DateFrom", "TimeFrom", "DateTo", "TimeTo",
        "IC_Name", "PreparedName", "PreparedDateTime",
    }
    assert required <= field_names


def test_ics207_has_command_staff():
    form = load_form(_ICS207_YAML)
    field_names = {f.name for f in form.fields}
    assert "IC_Name" in field_names
    assert "Deputy_IC" in field_names
    assert "Safety_Officer" in field_names
    assert "Liaison_Officer" in field_names
    assert "PIO" in field_names


def test_ics207_has_operations_section():
    form = load_form(_ICS207_YAML)
    field_names = {f.name for f in form.fields}
    assert "Ops_Chief" in field_names
    assert "Ops_Deputy" in field_names
    assert "Branch1_Dir" in field_names
    assert "Branch2_Dir" in field_names
    assert "Branch3_Dir" in field_names


def test_ics207_has_planning_section():
    form = load_form(_ICS207_YAML)
    field_names = {f.name for f in form.fields}
    assert "Plan_Chief" in field_names
    assert "Resources_UL" in field_names
    assert "Situation_UL" in field_names
    assert "Docs_UL" in field_names


def test_ics207_has_logistics_section():
    form = load_form(_ICS207_YAML)
    field_names = {f.name for f in form.fields}
    assert "Log_Chief" in field_names
    assert "Support_Dir" in field_names
    assert "Service_Dir" in field_names
    assert "Comms_UL" in field_names


def test_ics207_has_finance_section():
    form = load_form(_ICS207_YAML)
    field_names = {f.name for f in form.fields}
    assert "Finance_Chief" in field_names
    assert "Time_UL" in field_names
    assert "Cost_UL" in field_names


def test_ics207_ic_name_required():
    form = load_form(_ICS207_YAML)
    ic = next(f for f in form.fields if f.name == "IC_Name")
    assert ic.required is True


def test_ics207_subject_template_contains_incident_name():
    form = load_form(_ICS207_YAML)
    assert "Incident_Name" in form.subject_template


def test_ics207_body_template_contains_key_sections():
    form = load_form(_ICS207_YAML)
    assert "ICS 207" in form.body_template
    assert "INCIDENT ORGANIZATION CHART" in form.body_template
    assert "OPERATIONS SECTION" in form.body_template
    assert "PLANNING SECTION" in form.body_template
    assert "LOGISTICS SECTION" in form.body_template
    assert "FINANCE" in form.body_template
