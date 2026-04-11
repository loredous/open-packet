from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class FormLoadError(Exception):
    pass


@dataclass
class FormField:
    name: str
    label: str
    description: str = ""
    type: str = "text"
    choices: list[str] = field(default_factory=list)
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    format: Optional[str] = None
    auto_populate: bool = False
    computed_from: Optional[str] = None  # Name of field whose value drives this field
    compute: str = ""  # Computation type, e.g. "word_count"


@dataclass
class FormDefinition:
    name: str
    category: str
    fields: list[FormField]
    subject_template: str
    body_template: str
    source_path: Optional[Path] = None


def _parse_field(raw: object) -> FormField:
    if not isinstance(raw, dict):
        raise FormLoadError("Each field must be a YAML mapping")
    if "name" not in raw:
        raise FormLoadError("Field missing required key 'name'")
    if "label" not in raw:
        raise FormLoadError(f"Field '{raw['name']}' missing required key 'label'")
    return FormField(
        name=raw["name"],
        label=raw["label"],
        description=raw.get("description", ""),
        type=raw.get("type", "text"),
        choices=raw.get("choices", []),
        required=raw.get("required", False),
        min_length=raw.get("min_length"),
        max_length=raw.get("max_length"),
        pattern=raw.get("pattern"),
        format=raw.get("format"),
        auto_populate=raw.get("auto_populate", False),
        computed_from=raw.get("computed_from"),
        compute=raw.get("compute", ""),
    )


def load_form(path: Path) -> FormDefinition:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise FormLoadError(f"Failed to read/parse {path}: {e}") from e

    if not isinstance(data, dict):
        raise FormLoadError(f"{path}: expected a YAML mapping at top level")

    for key in ("name", "category", "fields", "subject_template", "body_template"):
        if key not in data:
            raise FormLoadError(f"{path}: missing required key '{key}'")

    if not isinstance(data["fields"], list):
        raise FormLoadError(f"{path}: 'fields' must be a list")

    if not data["fields"]:
        raise FormLoadError(f"{path}: 'fields' must contain at least one field")

    fields = [_parse_field(f) for f in data["fields"]]

    return FormDefinition(
        name=data["name"],
        category=data["category"],
        fields=fields,
        subject_template=data["subject_template"],
        body_template=data["body_template"],
        source_path=path,
    )


def discover_forms(forms_dir: Path) -> list[FormDefinition]:
    if not forms_dir.exists():
        return []
    results = []
    for yaml_path in sorted(forms_dir.rglob("*.yaml")):
        try:
            results.append(load_form(yaml_path))
        except FormLoadError as e:
            logger.warning("Skipping form %s: %s", yaml_path, e)
    return results
