from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


class ProfileParseError(ValueError):
    """A malformed or structurally unusable profile."""


@dataclass(frozen=True)
class Rebind:
    input: str | None
    attributes: dict[str, str]


@dataclass
class Action:
    name: str | None
    rebinds: list[Rebind] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    unknown_elements: list[ET.Element] = field(default_factory=list)


@dataclass
class ActionMap:
    name: str | None
    actions: list[Action] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    unknown_elements: list[ET.Element] = field(default_factory=list)


@dataclass
class ProfileWarning:
    code: str
    message: str
    path: str | None = None


@dataclass
class CustomisationUIHeader:
    attributes: dict[str, str] = field(default_factory=dict)
    devices: list[dict[str, str]] = field(default_factory=list)
    categories: list[dict[str, str]] = field(default_factory=list)
    unknown_elements: list[ET.Element] = field(default_factory=list)


@dataclass
class Profile:
    root_attributes: dict[str, str]
    profile_name: str | None
    header: CustomisationUIHeader | None
    action_maps: list[ActionMap]
    warnings: list[ProfileWarning] = field(default_factory=list)
    unknown_tokens: list[str] = field(default_factory=list)
    unknown_elements: list[ET.Element] = field(default_factory=list)
    source_path: Path | None = None
    _root: ET.Element | None = field(default=None, repr=False, compare=False)

    def actions(self) -> Iterable[tuple[ActionMap, Action]]:
        for action_map in self.action_maps:
            for action in action_map.actions:
                yield action_map, action

    def find_action(self, action_name: str, action_map_name: str | None = None) -> list[Action]:
        matches: list[Action] = []
        for action_map in self.action_maps:
            if action_map_name is not None and action_map.name != action_map_name:
                continue
            matches.extend(action for action in action_map.actions if action.name == action_name)
        return matches

    def to_xml_bytes(self, encoding: str = "utf-8") -> bytes:
        if self._root is None:
            raise RuntimeError("Profile has no source XML document")
        return ET.tostring(self._root, encoding=encoding, xml_declaration=True)


def _warning_add(warnings: list[ProfileWarning], code: str, message: str, path: str | None = None) -> None:
    warning = ProfileWarning(code=code, message=message, path=path)
    if warning not in warnings:
        warnings.append(warning)


def _known_input_token(token: str) -> bool:
    first_part = token.strip().split("+", 1)[0]
    device = first_part.split("_", 1)[0].lower()
    return bool(re.fullmatch(r"(kb\d*|mouse\d*|js\d*|gp\d*|gamepad\d*|xbox\d*|ps\d*)", device))


def parse_profile(source: str | bytes | Path) -> Profile:
    source_path: Path | None = None
    if isinstance(source, Path):
        source_path = source
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise ProfileParseError(f"Could not read profile '{source}': {exc}") from exc
    elif isinstance(source, str):
        path = Path(source)
        if "\x00" not in source and path.is_file():
            source_path = path
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise ProfileParseError(f"Could not read profile '{source}': {exc}") from exc
        else:
            data = source.encode("utf-8")
    else:
        data = source

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        location = f" at line {exc.position[0]}, column {exc.position[1]}" if exc.position else ""
        raise ProfileParseError(f"Malformed XML{location}: {exc}") from exc

    if root.tag != "ActionMaps":
        raise ProfileParseError(
            f"Invalid profile root: expected 'ActionMaps', found '{root.tag}'. "
            "This does not appear to be a Star Citizen action-map profile."
        )

    warnings: list[ProfileWarning] = []
    unknown_tokens: list[str] = []
    unknown_elements: list[ET.Element] = []
    root_attributes = dict(root.attrib)
    profile_name = root_attributes.get("profileName")

    header: CustomisationUIHeader | None = None
    action_maps: list[ActionMap] = []

    allowed_root_children = {"CustomisationUIHeader", "options", "modifiers", "actionmap"}
    for index, element in enumerate(root):
        if element.tag not in allowed_root_children:
            unknown_elements.append(copy.deepcopy(element))
            _warning_add(
                warnings,
                "unknown_xml_element",
                f"Unknown XML element '{element.tag}' was preserved.",
                f"/ActionMaps/{element.tag}[{index}]",
            )

        if element.tag == "CustomisationUIHeader":
            header = CustomisationUIHeader(attributes=dict(element.attrib))
            for child in element:
                if child.tag == "devices":
                    header.devices.extend(dict(device.attrib) for device in child)
                elif child.tag == "categories":
                    header.categories.extend(dict(category.attrib) for category in child)
                else:
                    header.unknown_elements.append(copy.deepcopy(child))
                    _warning_add(
                        warnings,
                        "unknown_xml_element",
                        f"Unknown XML element '{child.tag}' in CustomisationUIHeader was preserved.",
                        f"/ActionMaps/CustomisationUIHeader/{child.tag}",
                    )

        elif element.tag == "actionmap":
            action_map = ActionMap(name=element.get("name"), attributes=dict(element.attrib))
            for action_element in element:
                if action_element.tag != "action":
                    action_map.unknown_elements.append(copy.deepcopy(action_element))
                    _warning_add(
                        warnings,
                        "unknown_xml_element",
                        f"Unknown XML element '{action_element.tag}' in action map "
                        f"'{action_map.name}' was preserved.",
                        f"/ActionMaps/actionmap[@name='{action_map.name}']/{action_element.tag}",
                    )
                    continue

                action = Action(
                    name=action_element.get("name"),
                    attributes=dict(action_element.attrib),
                )
                if action.name is None:
                    _warning_add(
                        warnings,
                        "missing_action_name",
                        f"Action in map '{action_map.name}' has no name attribute.",
                        f"/ActionMaps/actionmap[@name='{action_map.name}']/action",
                    )
                for rebind_element in action_element:
                    if rebind_element.tag != "rebind":
                        action.unknown_elements.append(copy.deepcopy(rebind_element))
                        _warning_add(
                            warnings,
                            "unknown_xml_element",
                            f"Unknown XML element '{rebind_element.tag}' in action "
                            f"'{action.name}' was preserved.",
                            f"/ActionMaps/actionmap[@name='{action_map.name}']/action[@name='{action.name}']",
                        )
                        continue
                    rebind = Rebind(
                        input=rebind_element.get("input"),
                        attributes=dict(rebind_element.attrib),
                    )
                    action.rebinds.append(rebind)
                    if rebind.input is None:
                        _warning_add(
                            warnings,
                            "missing_rebind_input",
                            f"Rebind for action '{action.name}' has no input attribute.",
                            f"/ActionMaps/actionmap[@name='{action_map.name}']/action[@name='{action.name}']/rebind",
                        )
                    elif rebind.input.strip():
                        if not _known_input_token(rebind.input):
                            first_part = rebind.input.strip().split("+", 1)[0]
                            device = first_part.split("_", 1)[0]
                            if rebind.input not in unknown_tokens:
                                unknown_tokens.append(rebind.input)
                            _warning_add(
                                warnings,
                                "unknown_input_token",
                                f"Input token '{rebind.input}' contains unknown device/prefix '{device}'.",
                                f"/ActionMaps/actionmap[@name='{action_map.name}']/action[@name='{action.name}']/rebind",
                            )
                action_map.actions.append(action)
            action_maps.append(action_map)

    if not action_maps:
        _warning_add(
            warnings,
            "missing_action_maps",
            "The profile contains no actionmap elements.",
        )

    return Profile(
        root_attributes=root_attributes,
        profile_name=profile_name,
        header=header,
        action_maps=action_maps,
        warnings=warnings,
        unknown_tokens=unknown_tokens,
        unknown_elements=unknown_elements,
        source_path=source_path,
        _root=root,
    )


def parse_profile_file(path: str | Path) -> Profile:
    return parse_profile(Path(path))


def parse_profile_text(text: str) -> Profile:
    return parse_profile(text)


class ProfileStore:
    def __init__(self, profile: Profile | None = None) -> None:
        self.current_profile = profile

    def open(self, source: str | bytes | Path) -> Profile:
        parsed = parse_profile(source)
        self.current_profile = parsed
        return parsed
