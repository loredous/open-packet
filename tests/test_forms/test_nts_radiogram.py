"""Tests for the NTS Radiogram form definition and computed-field support."""
from __future__ import annotations
from pathlib import Path

import pytest

from open_packet.forms.loader import FormField, FormDefinition, load_form, discover_forms
from open_packet.forms.validator import validate_field, validate_form
from open_packet.ui.tui.screens.form_fill import _compute_word_count

# Resolve the NTS form YAML from the repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_NTS_YAML = _REPO_ROOT / "forms" / "NTS Forms" / "nts_radiogram.yaml"


# ---------------------------------------------------------------------------
# Hard-fail if the form YAML is missing — never silently skip
# ---------------------------------------------------------------------------

def test_nts_yaml_present():
    """Fail fast if the NTS Radiogram YAML is missing or was renamed."""
    assert _NTS_YAML.exists(), (
        f"NTS radiogram YAML not found at {_NTS_YAML}. "
        "Was the file moved or deleted?"
    )


# ---------------------------------------------------------------------------
# Word-count helper
# ---------------------------------------------------------------------------

def test_word_count_empty():
    assert _compute_word_count("") == "0"


def test_word_count_whitespace_only():
    assert _compute_word_count("   ") == "0"


def test_word_count_single_word():
    assert _compute_word_count("hello") == "1"


def test_word_count_multiple_words():
    assert _compute_word_count("hello world foo") == "3"


def test_word_count_extra_whitespace():
    assert _compute_word_count("  hello   world  ") == "2"


# ---------------------------------------------------------------------------
# FormField: computed_from / compute attributes load correctly
# ---------------------------------------------------------------------------

_COMPUTED_YAML = """\
name: Test Computed
category: Test
fields:
  - name: message
    label: Message
    type: textarea
    required: true
  - name: word_count
    label: Word Count
    type: text
    required: true
    computed_from: message
    compute: word_count
subject_template: "{{ word_count }} words"
body_template: "{{ message }}"
"""


def test_form_field_computed_from_loaded(tmp_path):
    f = tmp_path / "computed.yaml"
    f.write_text(_COMPUTED_YAML)
    form = load_form(f)
    wc_field = next(fld for fld in form.fields if fld.name == "word_count")
    assert wc_field.computed_from == "message"
    assert wc_field.compute == "word_count"


def test_form_field_non_computed_defaults(tmp_path):
    f = tmp_path / "plain.yaml"
    f.write_text(_COMPUTED_YAML)
    form = load_form(f)
    msg_field = next(fld for fld in form.fields if fld.name == "message")
    assert msg_field.computed_from is None
    assert msg_field.compute == ""


# ---------------------------------------------------------------------------
# NTS Radiogram YAML loads correctly
# ---------------------------------------------------------------------------

def test_nts_radiogram_loads():
    form = load_form(_NTS_YAML)
    assert form.name == "NTS Radiogram"
    assert form.category == "NTS Forms"


def test_nts_radiogram_has_required_fields():
    form = load_form(_NTS_YAML)
    field_names = {f.name for f in form.fields}
    required = {
        "message_number", "precedence", "handling_instructions",
        "station_of_origin", "check", "place_of_origin", "datetime_filed",
        "to_name", "to_address", "message_text", "signature",
    }
    assert required <= field_names


def test_nts_radiogram_precedence_choices():
    form = load_form(_NTS_YAML)
    prec = next(f for f in form.fields if f.name == "precedence")
    assert set(prec.choices) == {"R", "W", "P", "E"}


def test_nts_radiogram_check_computed():
    form = load_form(_NTS_YAML)
    check_field = next(f for f in form.fields if f.name == "check")
    assert check_field.computed_from == "message_text"
    assert check_field.compute == "word_count"


def test_nts_radiogram_handling_instructions_optional():
    form = load_form(_NTS_YAML)
    hi = next(f for f in form.fields if f.name == "handling_instructions")
    assert hi.required is False


# ---------------------------------------------------------------------------
# Validation: precedence codes
# ---------------------------------------------------------------------------

def test_precedence_valid_codes():
    form = load_form(_NTS_YAML)
    prec = next(f for f in form.fields if f.name == "precedence")
    for code in ("R", "W", "P", "E"):
        assert validate_field(prec, code) == []


def test_precedence_invalid_code():
    form = load_form(_NTS_YAML)
    prec = next(f for f in form.fields if f.name == "precedence")
    errors = validate_field(prec, "X")
    assert errors


# ---------------------------------------------------------------------------
# Validation: handling instructions pattern
# ---------------------------------------------------------------------------

def test_handling_instructions_empty_ok():
    form = load_form(_NTS_YAML)
    hi = next(f for f in form.fields if f.name == "handling_instructions")
    assert validate_field(hi, "") == []


def test_handling_instructions_single_valid():
    form = load_form(_NTS_YAML)
    hi = next(f for f in form.fields if f.name == "handling_instructions")
    assert validate_field(hi, "HXA") == []


def test_handling_instructions_multiple_valid():
    form = load_form(_NTS_YAML)
    hi = next(f for f in form.fields if f.name == "handling_instructions")
    assert validate_field(hi, "HXA HXC HXF") == []


def test_handling_instructions_invalid():
    form = load_form(_NTS_YAML)
    hi = next(f for f in form.fields if f.name == "handling_instructions")
    errors = validate_field(hi, "HXZ")  # Z is not a valid HX code
    assert errors


def test_handling_instructions_freeform_text_invalid():
    form = load_form(_NTS_YAML)
    hi = next(f for f in form.fields if f.name == "handling_instructions")
    errors = validate_field(hi, "HOLD FOR ARRIVAL")
    assert errors


# ---------------------------------------------------------------------------
# Validation: message number pattern
# ---------------------------------------------------------------------------

def test_message_number_valid():
    form = load_form(_NTS_YAML)
    mn = next(f for f in form.fields if f.name == "message_number")
    assert validate_field(mn, "42") == []


def test_message_number_invalid():
    form = load_form(_NTS_YAML)
    mn = next(f for f in form.fields if f.name == "message_number")
    errors = validate_field(mn, "not-a-number")
    assert errors
