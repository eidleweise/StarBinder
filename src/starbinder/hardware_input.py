from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AXIS_TOKENS = ("x", "y", "z", "rotz", "slider1", "slider2")


@dataclass(frozen=True)
class DetectedControl:
    query: str
    gamepad_id: str
    description: str
    control_type: str


def controls_from_gamepads(
    gamepads: list[dict[str, Any]],
    *,
    axis_threshold: float = 0.5,
) -> list[DetectedControl]:
    """Convert active browser Gamepad API controls to partial Star Citizen searches."""
    controls: list[DetectedControl] = []
    seen: set[tuple[str, str]] = set()

    for ordinal, gamepad in enumerate(gamepads):
        gamepad_id = str(gamepad.get("id") or "Unknown controller")
        try:
            instance = int(gamepad.get("index", ordinal)) + 1
        except (TypeError, ValueError):
            instance = ordinal + 1
        for index, button in enumerate(gamepad.get("buttons") or []):
            if not isinstance(button, dict):
                continue
            if not button.get("pressed") and float(button.get("value", 0.0)) < 0.8:
                continue
            query = f"js{instance}_button{index + 1}"
            key = ("button", query)
            if key not in seen:
                seen.add(key)
                controls.append(DetectedControl(
                    query=query,
                    gamepad_id=gamepad_id,
                    description=f"Joystick {instance} - Button {index + 1}",
                    control_type="button",
                ))

        for index, value in enumerate(gamepad.get("axes") or []):
            axis_value = float(value)
            if abs(axis_value) < axis_threshold:
                continue
            if index >= len(AXIS_TOKENS):
                continue
            token = AXIS_TOKENS[index]
            query = f"js{instance}_{token}"
            key = ("axis", query)
            if key not in seen:
                seen.add(key)
                direction = "positive" if axis_value > 0 else "negative"
                controls.append(DetectedControl(
                    query=query,
                    gamepad_id=gamepad_id,
                    description=f"Joystick {instance} - Axis {token.upper()} ({direction})",
                    control_type="axis",
                ))
    return controls
