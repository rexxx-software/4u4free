"""Small dependency-free parser for the KeyValues/VDF subset Steam uses."""

from __future__ import annotations

from typing import Dict, Iterator, List, Tuple, Union

from .errors import FourUFourFreeError

VDFValue = Union[str, Dict[str, "VDFValue"]]


class VDFParseError(FourUFourFreeError):
    pass


def _tokens(text: str) -> Iterator[str]:
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = length if newline == -1 else newline + 1
            continue
        if char in "{}":
            yield char
            index += 1
            continue
        if char == '"':
            index += 1
            value: List[str] = []
            while index < length:
                char = text[index]
                if char == '"':
                    index += 1
                    break
                if char == "\\" and index + 1 < length:
                    next_char = text[index + 1]
                    if next_char in ('"', "\\"):
                        value.append(next_char)
                        index += 2
                        continue
                value.append(char)
                index += 1
            else:
                raise VDFParseError("Unterminated quoted VDF value")
            yield "".join(value)
            continue

        start = index
        while index < length and not text[index].isspace() and text[index] not in '{}"':
            index += 1
        if start == index:
            raise VDFParseError(f"Unexpected character at offset {index}")
        yield text[start:index]


def parse_vdf(text: str) -> Dict[str, VDFValue]:
    """Parse VDF into nested dictionaries.

    Steam files in scope do not rely on duplicate keys, so later duplicate keys
    replace earlier ones. The parser accepts quoted and bare tokens plus // comments.
    """

    tokens = list(_tokens(text.lstrip("\ufeff")))

    def parse_object(index: int, nested: bool) -> Tuple[Dict[str, VDFValue], int]:
        result: Dict[str, VDFValue] = {}
        while index < len(tokens):
            token = tokens[index]
            if token == "}":
                if not nested:
                    raise VDFParseError("Unexpected closing brace")
                return result, index + 1
            if token == "{":
                raise VDFParseError("Unexpected opening brace; expected a key")

            key = token
            index += 1
            if index >= len(tokens):
                raise VDFParseError(f"Missing value for key {key!r}")
            value = tokens[index]
            if value == "{":
                child, index = parse_object(index + 1, True)
                result[key] = child
            elif value == "}":
                raise VDFParseError(f"Missing value for key {key!r}")
            else:
                result[key] = value
                index += 1
        if nested:
            raise VDFParseError("Missing closing brace")
        return result, index

    parsed, final_index = parse_object(0, False)
    if final_index != len(tokens):
        raise VDFParseError("Unexpected trailing tokens")
    return parsed


def read_vdf(path) -> Dict[str, VDFValue]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FourUFourFreeError(f"Could not read {path}: {exc}") from exc
    return parse_vdf(text)


def get_mapping(mapping: Dict[str, VDFValue], key: str) -> Dict[str, VDFValue]:
    value = next((value for name, value in mapping.items() if name.lower() == key.lower()), {})
    return value if isinstance(value, dict) else {}


def get_string(mapping: Dict[str, VDFValue], key: str, default: str = "") -> str:
    value = next((value for name, value in mapping.items() if name.lower() == key.lower()), default)
    return value if isinstance(value, str) else default

