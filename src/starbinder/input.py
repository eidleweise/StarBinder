from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class InputPart:
    raw: str
    display: str
    kind: str


@dataclass(frozen=True)
class ParsedInput:
    raw: str
    parts: tuple[InputPart, ...]
    display: str
    kind: str
    is_bound: bool


TOKEN_DISPLAY = {
    "lctrl": "Left Ctrl",
    "rctrl": "Right Ctrl",
    "lalt": "Left Alt",
    "ralt": "Right Alt",
    "lshift": "Left Shift",
    "rshift": "Right Shift",
    "mouse1": "Mouse 1",
    "mouse2": "Mouse 2",
    "mouse3": "Mouse 3",
    "mouse4": "Mouse 4",
    "mouse5": "Mouse 5",
    "lbracket": "[",
    "rbracket": "]",
}


def _humanize(token: str) -> str:
    acronyms = {
        "ifcs": "IFCS",
        "mfd": "MFD",
        "esp": "ESP",
        "qdrive": "Quantum Drive",
    }
    if token.lower() in acronyms:
        return acronyms[token.lower()]
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token.replace("_", " "))
    return " ".join(word.capitalize() for word in words.split())


def parse_input(raw: str | None) -> ParsedInput:
    if raw is None or not raw.strip():
        return ParsedInput(raw or "", (), "(No binding)", "none", False)

    text = raw.strip()
    if re.fullmatch(r"(?:kb\d*|js\d*|gp\d*|mouse)\s*_", text, re.IGNORECASE):
        return ParsedInput(raw=raw, parts=(), display="(No binding)", kind="none", is_bound=False)
    rendered: list[InputPart] = []
    kinds: set[str] = set()

    for component in text.split("+"):
        token = component.strip()
        if not token:
            continue
        lower = token.lower()
        kind = "keyboard"
        display = TOKEN_DISPLAY.get(lower.rsplit("_", 1)[-1], "")

        match = re.fullmatch(r"(kb\d*)_(.+)", lower)
        if match:
            key = match.group(2)
            if not display:
                display = {
                    "space": "Space",
                    "enter": "Enter",
                    "escape": "Escape",
                    "tab": "Tab",
                    "backspace": "Backspace",
                    "np_3": "Numpad 3",
                    "np_7": "Numpad 7",
                }.get(key, _humanize(key))
            kind = "keyboard"
        else:
            joystick = re.fullmatch(r"(?:js)(\d+)_(.+)", lower)
            if joystick:
                kind = "axis" if joystick.group(2).startswith(("x", "y", "z", "rot", "slider")) else "joystick"
                suffix = joystick.group(2)
                hat = re.fullmatch(r"hat(\d+)_(up|down|left|right)", suffix)
                if hat:
                    display = f"Joystick {joystick.group(1)} - Hat {hat.group(1)} {_humanize(hat.group(2))}"
                else:
                    button = re.fullmatch(r"button(\d+)", suffix)
                    if button:
                        display = f"Joystick {joystick.group(1)} - Button {button.group(1)}"
                    elif suffix.startswith("rotz"):
                        display = f"Joystick {joystick.group(1)} - Twist/Rudder Axis"
                    else:
                        display = f"Joystick {joystick.group(1)} - {_humanize(suffix)}"
            else:
                mouse = re.fullmatch(r"(?:mouse|kb\d*)_(mouse\d+|.+)", lower)
                if mouse and (mouse.group(1).startswith("mouse") or "mouse" in lower):
                    kind = "mouse"
                    display = _humanize(mouse.group(1))
                else:
                    gamepad = re.fullmatch(r"(?:gp|gamepad)(\d*)_(.+)", lower)
                    if gamepad:
                        kind = "gamepad"
                        display = f"Gamepad - {_humanize(gamepad.group(2))}"
                    else:
                        kind = "unknown"
                        display = _humanize(token)
        rendered.append(InputPart(raw=token, display=display, kind=kind))
        kinds.add(kind)

    kind = "axis" if "axis" in kinds and len(kinds) == 1 else (
        "mouse" if kinds == {"mouse"} else
        "gamepad" if kinds == {"gamepad"} else
        "joystick" if kinds == {"joystick"} else
        "keyboard" if kinds == {"keyboard"} else "unknown"
    )
    display = " + ".join(part.display for part in rendered)
    if kind == "axis":
        display = f"(Axis) {display}"
    return ParsedInput(raw=raw, parts=tuple(rendered), display=display, kind=kind, is_bound=True)


def normalize_input(raw: str | None) -> str:
    if raw is None:
        return ""
    return " ".join(parse_input(raw).display.lower().replace("-", " ").split())
