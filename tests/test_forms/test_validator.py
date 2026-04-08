import pytest
from open_packet.forms.loader import FormField, FormDefinition
from open_packet.forms.validator import validate_field, validate_form


def _field(**kwargs) -> FormField:
    return FormField(name="f", label="F", **kwargs)


def _form(*fields: FormField) -> FormDefinition:
    return FormDefinition(
        name="T", category="C",
        fields=list(fields),
        subject_template="x",
        body_template="y",
    )


# --- required ---

def test_required_fails_on_empty_string():
    errors = validate_field(_field(required=True), "")
    assert len(errors) == 1
    assert "required" in errors[0].lower()


def test_required_fails_on_whitespace_only():
    errors = validate_field(_field(required=True), "   ")
    assert len(errors) == 1


def test_required_passes_with_value():
    assert validate_field(_field(required=True), "hello") == []


# --- min_length ---

def test_min_length_fails():
    errors = validate_field(_field(min_length=5), "hi")
    assert len(errors) == 1
    assert "5" in errors[0]


def test_min_length_passes_exact():
    assert validate_field(_field(min_length=3), "abc") == []


def test_min_length_passes_longer():
    assert validate_field(_field(min_length=3), "abcdef") == []


def test_min_length_counts_raw_value_including_whitespace():
    # Values feed into templates verbatim, so raw length is checked (not stripped)
    errors = validate_field(_field(min_length=4), "  a")  # 3 chars raw, fails
    assert len(errors) == 1


# --- max_length ---

def test_max_length_fails():
    errors = validate_field(_field(max_length=3), "toolong")
    assert len(errors) == 1
    assert "3" in errors[0]


def test_max_length_passes_exact():
    assert validate_field(_field(max_length=3), "abc") == []


def test_max_length_passes_shorter():
    assert validate_field(_field(max_length=10), "ok") == []


# --- pattern ---

def test_pattern_fails():
    errors = validate_field(_field(pattern=r"^\d+$"), "abc")
    assert len(errors) == 1


def test_pattern_passes():
    assert validate_field(_field(pattern=r"^\d+$"), "123") == []


def test_pattern_must_match_full_value():
    errors = validate_field(_field(pattern=r"\d+"), "abc123")
    # fullmatch required — partial match not enough
    assert len(errors) == 1


# --- choices ---

def test_choices_fails_on_unknown_value():
    errors = validate_field(_field(choices=["Low", "High"]), "Medium")
    assert len(errors) == 1
    assert "Low" in errors[0] or "High" in errors[0]


def test_choices_passes_on_valid_value():
    assert validate_field(_field(choices=["Low", "High"]), "Low") == []


# --- empty non-required field skips other checks ---

def test_empty_non_required_skips_min_length():
    assert validate_field(_field(min_length=5), "") == []


def test_empty_non_required_skips_pattern():
    assert validate_field(_field(pattern=r"^\d+$"), "") == []


def test_empty_non_required_skips_choices():
    assert validate_field(_field(choices=["Low", "High"]), "") == []


# --- validate_form ---

def test_validate_form_returns_per_field_errors():
    form = _form(
        FormField(name="a", label="A", required=True),
        FormField(name="b", label="B", max_length=3),
    )
    errors = validate_form(form, {"a": "", "b": "toolong"})
    assert errors["a"]
    assert errors["b"]


def test_validate_form_no_errors():
    form = _form(
        FormField(name="a", label="A", required=True),
    )
    errors = validate_form(form, {"a": "hello"})
    assert errors == {"a": []}


def test_validate_form_missing_field_value_treated_as_empty():
    form = _form(FormField(name="a", label="A", required=True))
    errors = validate_form(form, {})
    assert errors["a"]
