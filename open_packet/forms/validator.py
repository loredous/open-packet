from __future__ import annotations
import re
from open_packet.forms.loader import FormField, FormDefinition


def validate_field(field: FormField, value: str) -> list[str]:
    errors: list[str] = []

    stripped = value.strip()

    if field.required and not stripped:
        errors.append("This field is required.")
        return errors  # skip further checks on empty required field

    # Skip other checks if value is empty and field is not required
    if not stripped:
        return []

    # Length checks use raw value (not stripped) — values feed directly into templates
    if field.min_length is not None and len(value) < field.min_length:
        errors.append(f"Must be at least {field.min_length} characters.")

    # Length checks use raw value (not stripped) — values feed directly into templates
    if field.max_length is not None and len(value) > field.max_length:
        errors.append(f"Must be no more than {field.max_length} characters.")

    if field.pattern is not None and not re.fullmatch(field.pattern, value):
        errors.append("Value does not match the required format.")

    if field.choices and value not in field.choices:
        options = ", ".join(field.choices)
        errors.append(f"Must be one of: {options}.")

    return errors


def validate_form(
    form: FormDefinition, values: dict[str, str]
) -> dict[str, list[str]]:
    return {
        f.name: validate_field(f, values.get(f.name, ""))
        for f in form.fields
    }
