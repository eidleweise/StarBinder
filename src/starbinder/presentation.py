from __future__ import annotations

import re
from dataclasses import dataclass
from collections import defaultdict

from .catalog import ActionCatalog
from .input import normalize_input, parse_input
from .profile import Profile


@dataclass(frozen=True)
class BindingEntry:
    action_map_name: str | None
    action_map_label: str
    action_name: str | None
    action_label: str
    description: str
    text_source: str
    raw_input: str | None
    display_input: str
    input_kind: str
    rebind_index: int
    all_rebinds: tuple[str, ...]

    @property
    def bound(self) -> bool:
        return self.raw_input is not None and bool(self.raw_input.strip())


class ProfileBrowser:
    def __init__(self, profile: Profile, catalog: ActionCatalog | None = None) -> None:
        self.profile = profile
        self.catalog = catalog or ActionCatalog.load()

    def entries(self) -> list[BindingEntry]:
        entries: list[BindingEntry] = []
        for action_map in self.profile.action_maps:
            map_text = self.catalog.resolve_map(action_map.name)
            for action in action_map.actions:
                action_text = self.catalog.resolve_action(action_map.name, action.name)
                all_rebinds = tuple(rebind.input or "" for rebind in action.rebinds)
                if action.rebinds:
                    for index, rebind in enumerate(action.rebinds):
                        parsed = parse_input(rebind.input)
                        entries.append(BindingEntry(
                            action_map_name=action_map.name,
                            action_map_label=map_text.label,
                            action_name=action.name,
                            action_label=action_text.label,
                            description=action_text.description,
                            text_source=action_text.source,
                            raw_input=rebind.input,
                            display_input=parsed.display,
                            input_kind=parsed.kind,
                            rebind_index=index,
                            all_rebinds=all_rebinds,
                        ))
                else:
                    parsed = parse_input(None)
                    entries.append(BindingEntry(
                        action_map_name=action_map.name,
                        action_map_label=map_text.label,
                        action_name=action.name,
                        action_label=action_text.label,
                        description=action_text.description,
                        text_source=action_text.source,
                        raw_input=None,
                        display_input=parsed.display,
                        input_kind=parsed.kind,
                        rebind_index=-1,
                        all_rebinds=(),
                    ))
        return entries

    def filter(
        self,
        binding_filter: str = "",
        name_filter: str = "",
        action_map_filter: str = "",
        device_filter: str = "",
        bound_filter: str | None = None,
    ) -> list[BindingEntry]:
        binding_query = normalize_input_text(binding_filter)
        name_query = normalize_input_text(name_filter)
        map_query = normalize_input_text(action_map_filter)
        device_query = normalize_input_text(device_filter)
        matches: list[BindingEntry] = []

        for entry in self.entries():
            if binding_query:
                axis_aliases: list[str] = []
                axis_match = re.fullmatch(r"js\d+_(x|y|z|rotz|slider\d+)", entry.raw_input or "", re.IGNORECASE)
                if axis_match:
                    axis_aliases.append(f"axis {axis_match.group(1).lower()}")
                haystacks = [
                    normalize_input_text(entry.display_input),
                    normalize_input_text(entry.raw_input or ""),
                    normalize_input(entry.raw_input),
                    *axis_aliases,
                ]
                if not any(binding_query_matches(binding_query, haystack) for haystack in haystacks):
                    continue
            if name_query:
                haystacks = [
                    normalize_input_text(entry.action_label),
                    normalize_input_text(entry.description),
                    normalize_input_text(entry.action_name or ""),
                    normalize_input_text(entry.action_map_label),
                    normalize_input_text(entry.action_map_name or ""),
                ]
                if not any(name_query in haystack for haystack in haystacks):
                    continue
            if map_query and map_query not in normalize_input_text(entry.action_map_name or ""):
                continue
            if device_query and device_query not in normalize_input_text(entry.input_kind):
                continue
            if bound_filter is not None:
                wants_bound = bound_filter.lower() in {"bound", "yes", "true"}
                if entry.bound != wants_bound:
                    continue
            matches.append(entry)
        return matches

    def grouped_entries(
        self,
        entries: list[BindingEntry] | None = None,
    ) -> dict[str, dict[str, list[BindingEntry]]]:
        groups: dict[str, dict[str, list[BindingEntry]]] = defaultdict(lambda: defaultdict(list))
        for entry in self.entries() if entries is None else entries:
            if entry.action_map_label == "Other":
                category = "Other"
                subsection = entry.action_map_name or "Unknown Map"
            elif " - " in entry.action_map_label:
                category, subsection = entry.action_map_label.split(" - ", 1)
            else:
                category, subsection = "General", entry.action_map_label
            groups[category][subsection].append(entry)
        return {category: dict(subsections) for category, subsections in groups.items()}


def normalize_input_text(text: str) -> str:
    normalized = (text or "").lower().replace("-", " ").replace("_", " ")
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"\b(?:js|joy|stick)\s*(\d+)\b", r"joystick \1", normalized)
    normalized = re.sub(r"\bjoystick\s*(\d+)\b", r"joystick \1", normalized)
    normalized = re.sub(r"\b(?:btn|bt)\s*(\d+)\b", r"button \1", normalized)
    normalized = re.sub(r"\bbutton\s*(\d+)\b", r"button \1", normalized)
    return normalized


def binding_query_matches(query: str, haystack: str) -> bool:
    button_match = re.fullmatch(r"button\s+(\d+)", query)
    if button_match:
        button_number = button_match.group(1)
        return re.search(
            rf"(?<![a-z0-9])button\s+{button_number}(?![a-z0-9])",
            haystack,
        ) is not None
    return query in haystack
