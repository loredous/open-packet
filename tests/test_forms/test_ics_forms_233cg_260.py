"""Tests for ICS Form 233CG (Incident Open Action Tracker) and ICS Form 260 (Resource Order)."""
from __future__ import annotations

from pathlib import Path

import pytest

from open_packet.forms.loader import load_form, discover_forms
from open_packet.forms.validator import validate_field, validate_form

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ICS233CG_YAML = _REPO_ROOT / "forms" / "ICS USA Forms" / "ics233cg_incident_open_action_tracker.yaml"
_ICS260_YAML = _REPO_ROOT / "forms" / "ICS USA Forms" / "ics260_resource_order.yaml"


# ---------------------------------------------------------------------------
# File presence checks
# ---------------------------------------------------------------------------

def test_ics233cg_yaml_present():
    assert _ICS233CG_YAML.exists(), (
        f"ICS 233CG YAML not found at {_ICS233CG_YAML}. "
        "Was the file moved or deleted?"
    )


def test_ics260_yaml_present():
    assert _ICS260_YAML.exists(), (
        f"ICS 260 YAML not found at {_ICS260_YAML}. "
        "Was the file moved or deleted?"
    )


# ---------------------------------------------------------------------------
# ICS 233CG – Incident Open Action Tracker
# ---------------------------------------------------------------------------

def test_ics233cg_loads():
    form = load_form(_ICS233CG_YAML)
    assert form.name == "ICS 233CG Incident Open Action Tracker"
    assert form.category == "ICS USA Forms"


def test_ics233cg_has_required_fields():
    form = load_form(_ICS233CG_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "Incident_Name",
        "DateTimeFrom",
        "DateTimeTo",
        "PreparedName",
        "PreparedDateTime",
    }
    assert required <= field_names


def test_ics233cg_required_fields_are_marked_required():
    form = load_form(_ICS233CG_YAML)
    required_fields = {f.name for f in form.fields if f.required}
    assert "Incident_Name" in required_fields
    assert "DateTimeFrom" in required_fields
    assert "DateTimeTo" in required_fields
    assert "PreparedName" in required_fields
    assert "PreparedDateTime" in required_fields


def test_ics233cg_has_eight_action_item_rows():
    form = load_form(_ICS233CG_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 9):
        assert f"Action{i}" in field_names, f"Missing Action{i}"
        assert f"Responsible{i}" in field_names, f"Missing Responsible{i}"
        assert f"DueDateTime{i}" in field_names, f"Missing DueDateTime{i}"
        assert f"Status{i}" in field_names, f"Missing Status{i}"
        assert f"Notes{i}" in field_names, f"Missing Notes{i}"


def test_ics233cg_action_fields_are_optional():
    form = load_form(_ICS233CG_YAML)
    for i in range(1, 9):
        action_field = next(f for f in form.fields if f.name == f"Action{i}")
        assert action_field.required is False, f"Action{i} should be optional"


def test_ics233cg_status_fields_have_choices():
    form = load_form(_ICS233CG_YAML)
    for i in range(1, 9):
        status_field = next(f for f in form.fields if f.name == f"Status{i}")
        assert set(status_field.choices) == {"Open", "In Progress", "Closed"}, (
            f"Status{i} has wrong choices: {status_field.choices}"
        )


def test_ics233cg_action_fields_are_textarea():
    form = load_form(_ICS233CG_YAML)
    for i in range(1, 9):
        action_field = next(f for f in form.fields if f.name == f"Action{i}")
        assert action_field.type == "textarea", f"Action{i} should be textarea"
        notes_field = next(f for f in form.fields if f.name == f"Notes{i}")
        assert notes_field.type == "textarea", f"Notes{i} should be textarea"


def test_ics233cg_subject_template_contains_incident_name():
    form = load_form(_ICS233CG_YAML)
    assert "Incident_Name" in form.subject_template


def test_ics233cg_body_template_contains_action_fields():
    form = load_form(_ICS233CG_YAML)
    assert "Action1" in form.body_template
    assert "Responsible1" in form.body_template
    assert "Status1" in form.body_template


def test_ics233cg_appears_in_discover_forms():
    forms_dir = _REPO_ROOT / "forms"
    forms = discover_forms(forms_dir)
    names = [f.name for f in forms]
    assert "ICS 233CG Incident Open Action Tracker" in names


def test_ics233cg_status_valid_choice():
    form = load_form(_ICS233CG_YAML)
    status_field = next(f for f in form.fields if f.name == "Status1")
    for choice in ("Open", "In Progress", "Closed"):
        errors = validate_field(status_field, choice)
        assert errors == [], f"Expected no errors for '{choice}', got {errors}"


def test_ics233cg_status_invalid_choice():
    form = load_form(_ICS233CG_YAML)
    status_field = next(f for f in form.fields if f.name == "Status1")
    errors = validate_field(status_field, "Unknown")
    assert errors, "Expected validation errors for invalid status choice"


# ---------------------------------------------------------------------------
# ICS 260 – Resource Order
# ---------------------------------------------------------------------------

def test_ics260_loads():
    form = load_form(_ICS260_YAML)
    assert form.name == "ICS 260 Resource Order"
    assert form.category == "ICS USA Forms"


def test_ics260_has_required_fields():
    form = load_form(_ICS260_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "Incident_Name",
        "Order_Number",
        "Request_DateTime",
        "Priority",
        "Requested_By",
        "PreparedName",
        "PreparedDateTime",
    }
    assert required <= field_names


def test_ics260_required_fields_are_marked_required():
    form = load_form(_ICS260_YAML)
    required_fields = {f.name for f in form.fields if f.required}
    assert "Incident_Name" in required_fields
    assert "Order_Number" in required_fields
    assert "Request_DateTime" in required_fields
    assert "Priority" in required_fields
    assert "Requested_By" in required_fields
    assert "PreparedName" in required_fields
    assert "PreparedDateTime" in required_fields


def test_ics260_has_five_resource_rows():
    form = load_form(_ICS260_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 6):
        assert f"Qty{i}" in field_names, f"Missing Qty{i}"
        assert f"KindType{i}" in field_names, f"Missing KindType{i}"
        assert f"Description{i}" in field_names, f"Missing Description{i}"
        assert f"ReportLocation{i}" in field_names, f"Missing ReportLocation{i}"
        assert f"ReportDateTime{i}" in field_names, f"Missing ReportDateTime{i}"
        assert f"ETA{i}" in field_names, f"Missing ETA{i}"
        assert f"ItemOrderNo{i}" in field_names, f"Missing ItemOrderNo{i}"


def test_ics260_resource_rows_are_optional():
    form = load_form(_ICS260_YAML)
    for i in range(1, 6):
        qty_field = next(f for f in form.fields if f.name == f"Qty{i}")
        assert qty_field.required is False, f"Qty{i} should be optional"
        desc_field = next(f for f in form.fields if f.name == f"Description{i}")
        assert desc_field.required is False, f"Description{i} should be optional"


def test_ics260_has_logistics_fields():
    form = load_form(_ICS260_YAML)
    field_names = {f.name for f in form.fields}
    assert "Logistics_Order_Number" in field_names
    assert "Confirmed_By" in field_names
    assert "Confirmed_DateTime" in field_names
    assert "Logistics_Notes" in field_names


def test_ics260_has_finance_fields():
    form = load_form(_ICS260_YAML)
    field_names = {f.name for f in form.fields}
    assert "Finance_Approval" in field_names
    assert "Finance_DateTime" in field_names


def test_ics260_priority_field_has_choices():
    form = load_form(_ICS260_YAML)
    priority_field = next(f for f in form.fields if f.name == "Priority")
    assert set(priority_field.choices) == {"Routine", "Priority", "Immediate", "Critical"}


def test_ics260_priority_valid_choice():
    form = load_form(_ICS260_YAML)
    priority_field = next(f for f in form.fields if f.name == "Priority")
    for choice in ("Routine", "Priority", "Immediate", "Critical"):
        errors = validate_field(priority_field, choice)
        assert errors == [], f"Expected no errors for '{choice}', got {errors}"


def test_ics260_priority_invalid_choice():
    form = load_form(_ICS260_YAML)
    priority_field = next(f for f in form.fields if f.name == "Priority")
    errors = validate_field(priority_field, "ASAP")
    assert errors, "Expected validation errors for invalid priority choice"


def test_ics260_description_fields_are_textarea():
    form = load_form(_ICS260_YAML)
    for i in range(1, 6):
        desc_field = next(f for f in form.fields if f.name == f"Description{i}")
        assert desc_field.type == "textarea", f"Description{i} should be textarea"


def test_ics260_logistics_notes_is_textarea():
    form = load_form(_ICS260_YAML)
    notes_field = next(f for f in form.fields if f.name == "Logistics_Notes")
    assert notes_field.type == "textarea"


def test_ics260_delivery_location_is_textarea():
    form = load_form(_ICS260_YAML)
    delivery_field = next(f for f in form.fields if f.name == "Delivery_Location")
    assert delivery_field.type == "textarea"


def test_ics260_subject_template_contains_incident_name_and_order():
    form = load_form(_ICS260_YAML)
    assert "Incident_Name" in form.subject_template
    assert "Order_Number" in form.subject_template


def test_ics260_body_template_contains_key_fields():
    form = load_form(_ICS260_YAML)
    assert "Priority" in form.body_template
    assert "Qty1" in form.body_template
    assert "Logistics_Order_Number" in form.body_template
    assert "Finance_Approval" in form.body_template


def test_ics260_appears_in_discover_forms():
    forms_dir = _REPO_ROOT / "forms"
    forms = discover_forms(forms_dir)
    names = [f.name for f in forms]
    assert "ICS 260 Resource Order" in names
