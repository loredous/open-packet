"""Tests for ICS Forms 215A, 217A, and 218 YAML definitions."""
from __future__ import annotations

from pathlib import Path

import pytest

from open_packet.forms.loader import load_form, discover_forms

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ICS_DIR = _REPO_ROOT / "forms" / "ICS USA Forms"

_ICS215A_YAML = _ICS_DIR / "ics215a_iap_safety_analysis.yaml"
_ICS217A_YAML = _ICS_DIR / "ics217a_comm_resource_availability.yaml"
_ICS218_YAML = _ICS_DIR / "ics218_support_vehicle_inventory.yaml"


# ---------------------------------------------------------------------------
# Presence checks — fail fast if YAML files are missing
# ---------------------------------------------------------------------------

def test_ics215a_yaml_present():
    assert _ICS215A_YAML.exists(), f"ICS 215A YAML not found at {_ICS215A_YAML}"


def test_ics217a_yaml_present():
    assert _ICS217A_YAML.exists(), f"ICS 217A YAML not found at {_ICS217A_YAML}"


def test_ics218_yaml_present():
    assert _ICS218_YAML.exists(), f"ICS 218 YAML not found at {_ICS218_YAML}"


# ---------------------------------------------------------------------------
# ICS 215A – Incident Action Plan Safety Analysis
# ---------------------------------------------------------------------------

def test_ics215a_loads():
    form = load_form(_ICS215A_YAML)
    assert form.name == "ICS 215A IAP Safety Analysis"
    assert form.category == "ICS USA Forms"


def test_ics215a_has_required_fields():
    form = load_form(_ICS215A_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "IncidentName", "DateTimePrepared",
        "DateFrom", "TimeFrom", "DateTo", "TimeTo",
        "PreparedBy", "PreparedDateTime",
    }
    assert required <= field_names


def test_ics215a_has_hazard_risk_rows():
    form = load_form(_ICS215A_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 6):
        assert f"HazardRisk{i}" in field_names
        assert f"Mitigations{i}" in field_names
        assert f"AffectsWho{i}" in field_names


def test_ics215a_required_fields_marked():
    form = load_form(_ICS215A_YAML)
    required_map = {f.name: f.required for f in form.fields}
    assert required_map["IncidentName"] is True
    assert required_map["DateTimePrepared"] is True
    assert required_map["PreparedBy"] is True
    assert required_map["PreparedDateTime"] is True


def test_ics215a_optional_fields_not_required():
    form = load_form(_ICS215A_YAML)
    optional_map = {f.name: f.required for f in form.fields}
    assert optional_map["WeatherForecast"] is False
    assert optional_map["HazardRisk1"] is False
    assert optional_map["Mitigations1"] is False


def test_ics215a_weather_forecast_is_textarea():
    form = load_form(_ICS215A_YAML)
    field = next(f for f in form.fields if f.name == "WeatherForecast")
    assert field.type == "textarea"


def test_ics215a_subject_template_uses_key_fields():
    form = load_form(_ICS215A_YAML)
    assert "IncidentName" in form.subject_template
    assert "DateTimePrepared" in form.subject_template


def test_ics215a_body_template_contains_hazard_fields():
    form = load_form(_ICS215A_YAML)
    for i in range(1, 6):
        assert f"HazardRisk{i}" in form.body_template
        assert f"Mitigations{i}" in form.body_template
        assert f"AffectsWho{i}" in form.body_template


# ---------------------------------------------------------------------------
# ICS 217A – Communications Resource Availability Worksheet
# ---------------------------------------------------------------------------

def test_ics217a_loads():
    form = load_form(_ICS217A_YAML)
    assert form.name == "ICS 217A Comm Resource Availability Worksheet"
    assert form.category == "ICS USA Forms"


def test_ics217a_has_required_fields():
    form = load_form(_ICS217A_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "IncidentName", "DateTimePrepared",
        "DateFrom", "TimeFrom", "DateTo", "TimeTo",
        "PreparedBy", "PreparedDateTime",
    }
    assert required <= field_names


def test_ics217a_has_resource_rows():
    form = load_form(_ICS217A_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 7):
        assert f"ResourceType{i}" in field_names
        assert f"ResourceChannel{i}" in field_names
        assert f"ResourceFunction{i}" in field_names
        assert f"ResourceFreq{i}" in field_names
        assert f"ResourceInstructions{i}" in field_names


def test_ics217a_required_fields_marked():
    form = load_form(_ICS217A_YAML)
    required_map = {f.name: f.required for f in form.fields}
    assert required_map["IncidentName"] is True
    assert required_map["DateTimePrepared"] is True
    assert required_map["PreparedBy"] is True
    assert required_map["PreparedDateTime"] is True


def test_ics217a_resource_fields_not_required():
    form = load_form(_ICS217A_YAML)
    optional_map = {f.name: f.required for f in form.fields}
    for i in range(1, 7):
        assert optional_map[f"ResourceType{i}"] is False


def test_ics217a_subject_template_uses_key_fields():
    form = load_form(_ICS217A_YAML)
    assert "IncidentName" in form.subject_template
    assert "DateTimePrepared" in form.subject_template


def test_ics217a_body_template_contains_resource_fields():
    form = load_form(_ICS217A_YAML)
    for i in range(1, 7):
        assert f"ResourceType{i}" in form.body_template
        assert f"ResourceChannel{i}" in form.body_template
        assert f"ResourceFreq{i}" in form.body_template


# ---------------------------------------------------------------------------
# ICS 218 – Support Vehicle/Equipment Inventory
# ---------------------------------------------------------------------------

def test_ics218_loads():
    form = load_form(_ICS218_YAML)
    assert form.name == "ICS 218 Support Vehicle/Equipment Inventory"
    assert form.category == "ICS USA Forms"


def test_ics218_has_required_fields():
    form = load_form(_ICS218_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "IncidentName", "DateTimePrepared",
        "DateFrom", "TimeFrom", "DateTo", "TimeTo",
        "PreparedBy", "PreparedDateTime",
    }
    assert required <= field_names


def test_ics218_has_vehicle_rows():
    form = load_form(_ICS218_YAML)
    field_names = {f.name for f in form.fields}
    for i in range(1, 7):
        assert f"VehicleType{i}" in field_names
        assert f"VehicleMakeModel{i}" in field_names
        assert f"VehicleYear{i}" in field_names
        assert f"VehicleLicense{i}" in field_names
        assert f"VehicleAgency{i}" in field_names
        assert f"VehicleHomeBase{i}" in field_names


def test_ics218_required_fields_marked():
    form = load_form(_ICS218_YAML)
    required_map = {f.name: f.required for f in form.fields}
    assert required_map["IncidentName"] is True
    assert required_map["DateTimePrepared"] is True
    assert required_map["PreparedBy"] is True
    assert required_map["PreparedDateTime"] is True


def test_ics218_vehicle_fields_not_required():
    form = load_form(_ICS218_YAML)
    optional_map = {f.name: f.required for f in form.fields}
    for i in range(1, 7):
        assert optional_map[f"VehicleType{i}"] is False
        assert optional_map[f"VehicleAgency{i}"] is False


def test_ics218_subject_template_uses_key_fields():
    form = load_form(_ICS218_YAML)
    assert "IncidentName" in form.subject_template
    assert "DateTimePrepared" in form.subject_template


def test_ics218_body_template_contains_vehicle_fields():
    form = load_form(_ICS218_YAML)
    for i in range(1, 7):
        assert f"VehicleType{i}" in form.body_template
        assert f"VehicleMakeModel{i}" in form.body_template
        assert f"VehicleAgency{i}" in form.body_template


# ---------------------------------------------------------------------------
# Discovery: all three forms appear when scanning the forms directory
# ---------------------------------------------------------------------------

def test_all_three_forms_discovered():
    forms = discover_forms(_ICS_DIR)
    form_names = {f.name for f in forms}
    assert "ICS 215A IAP Safety Analysis" in form_names
    assert "ICS 217A Comm Resource Availability Worksheet" in form_names
    assert "ICS 218 Support Vehicle/Equipment Inventory" in form_names
