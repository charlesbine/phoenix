"""Extract schema fields from Starlark app files by parsing get_schema() functions.

This is a lightweight regex-based parser — it doesn't execute Starlark, just extracts
field definitions (id, name, desc, type, default, options) from the source text.
"""

import re
from pathlib import Path


# Maps schema.X() to a field type
FIELD_TYPES = {
    "Text": "text",
    "Toggle": "toggle",
    "Dropdown": "dropdown",
    "Location": "location",
    "DateTime": "datetime",
    "Color": "color",
    "Typeahead": "typeahead",
    "LocationBased": "location",
    "OAuth2": "oauth2",
    "PhotoSelect": "photo",
    "Generated": "generated",
}


def _find_options_in_file(text: str, var_name: str) -> list[dict]:
    """Find schema.Option() calls in a variable assignment like `varname = [...]`."""
    # Look for the variable assignment in the full file text
    pattern = rf"{re.escape(var_name)}\s*=\s*\[(.*?)\]"
    match = re.search(pattern, text, re.DOTALL)
    source = match.group(1) if match else ""
    return _extract_options(source)


def _extract_options(source: str) -> list[dict]:
    """Extract schema.Option(display=..., value=...) from a chunk of text."""
    options = []
    for opt_match in re.finditer(
        r'schema\.Option\((.*?)\)', source, re.DOTALL
    ):
        args = opt_match.group(1)
        display = re.search(r'display\s*=\s*"([^"]*)"', args)
        value = re.search(r'value\s*=\s*"([^"]*)"', args)
        if display and value:
            options.append({"display": display.group(1), "value": value.group(1)})
    return options


def parse_schema(star_path: Path) -> list[dict] | None:
    """Parse get_schema() from a .star file. Returns list of field dicts, or None if no schema."""
    text = star_path.read_text()

    # Find get_schema function body
    match = re.search(r"def get_schema\(\):(.*?)(?=\ndef |\Z)", text, re.DOTALL)
    if not match:
        return None

    body = match.group(1)
    fields = []

    # Find all schema.FieldType( starts, then extract args up to matching close paren
    for start_match in re.finditer(r"schema\.(\w+)\(", body):
        type_name = start_match.group(1)
        if type_name in ("Schema", "Option"):
            continue
        field_type = FIELD_TYPES.get(type_name, type_name.lower())

        # Find matching closing paren
        depth = 1
        pos = start_match.end()
        while pos < len(body) and depth > 0:
            if body[pos] == "(":
                depth += 1
            elif body[pos] == ")":
                depth -= 1
            pos += 1
        args_text = body[start_match.end():pos - 1]

        field: dict = {"type": field_type}

        # Extract named arguments
        for key in ("id", "name", "desc", "default", "icon"):
            val_match = re.search(rf'{key}\s*=\s*"([^"]*)"', args_text)
            if val_match:
                field[key] = val_match.group(1)
            else:
                # Try non-string values (True, False, numbers)
                val_match = re.search(rf"{key}\s*=\s*(\w+)", args_text)
                if val_match and key == "default":
                    val = val_match.group(1)
                    if val == "True":
                        field["default"] = "true"
                    elif val == "False":
                        field["default"] = "false"
                    else:
                        field["default"] = val

        # Extract options for Dropdown fields
        if field_type == "dropdown":
            # First try inline schema.Option() calls within this field's args
            options = _extract_options(args_text)
            if not options:
                # Try variable reference: options = someVar
                var_match = re.search(r"options\s*=\s*(\w+)", args_text)
                if var_match:
                    options = _find_options_in_file(text, var_match.group(1))
            if options:
                field["options"] = options
                # Clean up variable-reference defaults (e.g. "colorOpt" -> first option value)
                if "default" in field and not field["default"].startswith(("#", "true", "false")):
                    # Default references a variable — try to resolve index like colorOpt[3].value
                    idx_match = re.search(r"default\s*=\s*\w+\[(\d+)\]", args_text)
                    if idx_match:
                        idx = int(idx_match.group(1))
                        if idx < len(options):
                            field["default"] = options[idx]["value"]
                    elif options:
                        field["default"] = options[0]["value"]

        if "id" in field:
            fields.append(field)

    return fields if fields else None
