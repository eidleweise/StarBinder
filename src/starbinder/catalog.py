from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ResolvedText:
    label: str
    description: str
    source: str
    label_key: str | None = None
    description_key: str | None = None

    @property
    def is_curated(self) -> bool:
        return self.source in {"catalog", "curated", "translated"}

    @property
    def is_fallback(self) -> bool:
        return self.source in {"neutral", "fallback", "missing"}


def neutral_name(raw_name: str) -> str:
    words = raw_name.strip()
    words = re.sub(r"^v_", "", words)
    acronyms = {"ifcs": "IFCS", "mfd": "MFD", "esp": "ESP", "qdrive": "Quantum Drive"}
    direction = {
        "increase": "Increase", "decrease": "Decrease",
        "toggle": "Toggle", "cycle": "Cycle",
        "back": "Backward", "forward": "Forward",
        "left": "Left", "right": "Right",
    }
    output: list[str] = []
    for word in words.replace("-", "_").split("_"):
        if not word:
            continue
        lower = word.lower()
        output.append(acronyms.get(lower, direction.get(lower, word.capitalize())))
    return " ".join(output) or "Unknown Action"


class ActionCatalog:
    def __init__(
        self,
        catalog: Mapping[str, object] | None = None,
        locales: Mapping[str, Mapping[str, object]] | None = None,
        locale: str = "en-US",
    ) -> None:
        if catalog is None:
            data_path = Path(__file__).with_name("data") / "action_catalog.json"
            catalog = json.loads(data_path.read_text(encoding="utf-8"))
        if locales is None:
            locales = {}
            locale_dir = Path(__file__).with_name("data") / "locales"
            if locale_dir.exists():
                for path in locale_dir.glob("*.json"):
                    locales[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        self.catalog = catalog
        self.locales = locales
        self.locale = locale

    @staticmethod
    def load(locale: str = "en-US") -> "ActionCatalog":
        return ActionCatalog(locale=locale)

    def _locale_fallbacks(self, locale: str) -> tuple[str, ...]:
        candidates = [locale]
        if "-" in locale:
            candidates.append(locale.split("-", 1)[0])
        candidates.append("en-US")
        result: list[str] = []
        for candidate in candidates:
            if candidate not in result:
                result.append(candidate)
        return tuple(result)

    def resolve_map(self, map_name: str | None) -> ResolvedText:
        if not map_name:
            return ResolvedText("Other", "", "fallback")
        map_catalog = self.catalog.get("action_maps", {})
        entry = map_catalog.get(map_name)
        if not isinstance(entry, dict):
            return ResolvedText("Other", "", "fallback")
        key = entry.get("label_key")
        translated = self._resolve_key(key)
        if translated is not None:
            return ResolvedText(translated, "", "translated", key)
        return ResolvedText(neutral_name(map_name), "", "fallback")

    def resolve_action(self, map_name: str | None, action_name: str | None) -> ResolvedText:
        if not action_name:
            return ResolvedText("Unknown Action", "No action identifier is available.", "fallback")
        actions = self.catalog.get("actions", {})
        map_entry = actions.get(map_name, {}) if isinstance(actions, dict) else {}
        entry = map_entry.get(action_name) if isinstance(map_entry, dict) else None
        if not isinstance(entry, dict):
            return ResolvedText(neutral_name(action_name), "", "fallback")
        label_key = entry.get("label_key")
        description_key = entry.get("description_key")
        label = self._resolve_key(label_key)
        description = self._resolve_key(description_key)
        source = "translated" if label is not None or description is not None else "fallback"
        return ResolvedText(
            label if label is not None else neutral_name(action_name),
            description or "",
            source,
            label_key if isinstance(label_key, str) else None,
            description_key if isinstance(description_key, str) else None,
        )

    def _resolve_key(self, key: object) -> str | None:
        if not isinstance(key, str):
            return None
        parts = key.split(".")
        for locale in self._locale_fallbacks(self.locale):
            bundle = self.locales.get(locale)
            value: object = bundle
            for part in parts:
                if not isinstance(value, dict) or part not in value:
                    value = None
                    break
                value = value[part]
            if isinstance(value, str):
                return value
        return None
