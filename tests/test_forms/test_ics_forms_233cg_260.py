"""Tests for ICS Forms 233CG (Incident Open Action Tracker) and 260 (Resource Order)."""
from __future__ import annotations
from pathlib import Path

import pytest

from open_packet.forms.loader import load_form, discover_forms

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ICS_DIR = _REPO_ROOT / "forms" / "ICS USA Forms"
_ICS233CG_YAML = _ICS_DIR / "ics233cg_incident_open_action_tracker.yaml"
_ICS260_YAML = _ICS_DIR / "ics260_resource_order.yaml"


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


def test_ics233cg_required_fields():
    form = load_form(_ICS233CG_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "IncidentName", "DateFrom", "DateTo", "TimeFrom", "TimeTo",
        "PreparedBy", "PrepPosition", "PrepDateTime",
    }
    assert required <= field_names


def test_ics233cg_has_action_item_rows():
    form = load_form(_ICS233CG_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 11):
        assert f"Action{i}Description" in field_names, (
            f"Missing Action{i}Description field"
        )
        assert f"Action{i}Responsible" in field_names, (
            f"Missing Action{i}Responsible field"
        )
        assert f"Action{i}Status" in field_names, (
            f"Missing Action{i}Status field"
        )


def test_ics233cg_action_status_choices():
    form = load_form(_ICS233CG_YAML)
    status_field = next(f for f in form.fields if f.name == "Action1Status")
    assert set(status_field.choices) == {"Open", "In Progress", "Closed"}


def test_ics233cg_incident_name_required():
    form = load_form(_ICS233CG_YAML)
    incident_field = next(f for f in form.fields if f.name == "IncidentName")
    assert incident_field.required is True


def test_ics233cg_preparer_fields_required():
    form = load_form(_ICS233CG_YAML)
    required_names = {"PreparedBy", "PrepPosition", "PrepDateTime"}
    for f in form.fields:
        if f.name in required_names:
            assert f.required is True, f"{f.name} should be required"


def test_ics233cg_action_item_fields_optional():
    form = load_form(_ICS233CG_YAML)
    for f in form.fields:
        if f.name.startswith("Action"):
            assert f.required is False, f"{f.name} should be optional"


def test_ics233cg_subject_template_uses_incident_name_and_date():
    form = load_form(_ICS233CG_YAML)
    assert "IncidentName" in form.subject_template
    assert "DateFrom" in form.subject_template


def test_ics233cg_body_template_contains_all_action_items():
    form = load_form(_ICS233CG_YAML)
    for i in range(1, 11):
        assert f"Action{i}Description" in form.body_template
        assert f"Action{i}Status" in form.body_template


def test_ics233cg_discovered_by_discover_forms():
    forms = discover_forms(_ICS_DIR)
    names = [f.name for f in forms]
    assert "ICS 233CG Incident Open Action Tracker" in names


# ---------------------------------------------------------------------------
# ICS 260 – Resource Order
# ---------------------------------------------------------------------------

def test_ics260_loads():
    form = load_form(_ICS260_YAML)
    assert form.name == "ICS 260 Resource Order"
    assert form.category == "ICS USA Forms"


def test_ics260_required_fields():
    form = load_form(_ICS260_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "IncidentName", "DateTimePrepared",
        "DateFrom", "DateTo", "TimeFrom", "TimeTo",
        "OrderingManager",
        "PreparedBy", "PrepPosition", "PrepDateTime",
    }
    assert required <= field_names


def test_ics260_has_resource_order_rows():
    form = load_form(_ICS260_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 7):
        assert f"Order{i}KindType" in field_names, (
            f"Missing Order{i}KindType field"
        )
        assert f"Order{i}Quantity" in field_names, (
            f"Missing Order{i}Quantity field"
        )
        assert f"Order{i}ReportingLocation" in field_names, (
            f"Missing Order{i}ReportingLocation field"
        )
        assert f"Order{i}ETA" in field_names, (
            f"Missing Order{i}ETA field"
        )


def test_ics260_incident_name_required():
    form = load_form(_ICS260_YAML)
    incident_field = next(f for f in form.fields if f.name == "IncidentName")
    assert incident_field.required is True


def test_ics260_ordering_manager_required():
    form = load_form(_ICS260_YAML)
    om_field = next(f for f in form.fields if f.name == "OrderingManager")
    assert om_field.required is True


def test_ics260_preparer_fields_required():
    form = load_form(_ICS260_YAML)
    required_names = {"PreparedBy", "PrepPosition", "PrepDateTime"}
    for f in form.fields:
        if f.name in required_names:
            assert f.required is True, f"{f.name} should be required"


def test_ics260_order_rows_optional():
    form = load_form(_ICS260_YAML)
    for i in range(1, 7):
        for f in form.fields:
            if f.name.startswith(f"Order{i}"):
                assert f.required is False, f"{f.name} should be optional"


def test_ics260_incident_number_optional():
    form = load_form(_ICS260_YAML)
    field = next(f for f in form.fields if f.name == "IncidentNumber")
    assert field.required is False


def test_ics260_finance_admin_chief_optional():
    form = load_form(_ICS260_YAML)
    field = next(f for f in form.fields if f.name == "FinanceAdminChief")
    assert field.required is False


def test_ics260_subject_template_uses_incident_name_and_datetime():
    form = load_form(_ICS260_YAML)
    assert "IncidentName" in form.subject_template
    assert "DateTimePrepared" in form.subject_template


def test_ics260_body_template_contains_all_order_rows():
    form = load_form(_ICS260_YAML)
    for i in range(1, 7):
        assert f"Order{i}KindType" in form.body_template
        assert f"Order{i}ETA" in form.body_template


def test_ics260_body_template_contains_ordering_manager():
    form = load_form(_ICS260_YAML)
    assert "OrderingManager" in form.body_template


def test_ics260_body_template_contains_finance_admin():
    form = load_form(_ICS260_YAML)
    assert "FinanceAdminChief" in form.body_template


def test_ics260_discovered_by_discover_forms():
    forms = discover_forms(_ICS_DIR)
    names = [f.name for f in forms]
    assert "ICS 260 Resource Order" in names
