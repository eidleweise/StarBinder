import json
import logging
import sys
from pathlib import Path
from typing import Any

from nicegui import app, ui

from starbinder.logging_config import configure_logging
from starbinder.hardware_input import controls_from_gamepads
from starbinder.presentation import ProfileBrowser
from starbinder.profile import Profile, ProfileParseError, parse_profile_file


_current_profile: Profile | None = None
_profile_browser: ProfileBrowser | None = None
_profile_ui_state: dict[str, Any] | None = None
_logger = logging.getLogger(__name__)


def build_ui() -> None:
    global _profile_ui_state
    with ui.column().classes("w-full gap-4 p-4"):
        ui.label("StarBinder").classes("text-h4")
        with ui.row().classes("w-full gap-2"):
            ui.button("Open", on_click=open_profile_dialog).props("flat")
            ui.button("Clear", on_click=lambda: clear_filters()).props("flat")
        with ui.row().classes("w-full items-center gap-3"):
            binding_filter = ui.input(
                "Filter by binding (e.g. Joystick 1, js1_button3)",
                on_change=lambda _: refresh_profile(),
            ).props("clearable").classes("flex-1")
            name_filter = ui.input(
                "Filter by action",
                on_change=lambda _: refresh_profile(),
            ).props("clearable").classes("flex-1")
        with ui.row().classes("w-full items-center gap-2"):
            detect_button = ui.button("Detect joystick / gamepad input")
            stop_detect_button = ui.button("Stop detection").props("flat")
            capture_status = ui.label("Detection is off.")
        match_count = ui.label("Open a profile to browse bindings.")
        browser_container = ui.column().classes("w-full")
        capture_state = {"active": False}
        capture_timer = ui.timer(
            0.15,
            lambda: poll_gamepad(binding_filter, capture_status, capture_state, capture_timer),
            active=False,
        )
        detect_button.on_click(
            lambda: start_gamepad_detection(capture_timer, capture_state, capture_status)
        )
        stop_detect_button.on_click(
            lambda: stop_gamepad_detection(capture_timer, capture_state, capture_status)
        )
        _profile_ui_state = {
            "binding": binding_filter,
            "name": name_filter,
            "count": match_count,
            "container": browser_container,
            "capture_timer": capture_timer,
            "capture_state": capture_state,
            "capture_status": capture_status,
        }


def start_gamepad_detection(timer: Any, state: dict[str, Any], status: Any) -> None:
    state["active"] = True
    status.set_text("Move an axis or press a joystick/gamepad button…")
    timer.activate()


def stop_gamepad_detection(timer: Any, state: dict[str, Any], status: Any) -> None:
    state["active"] = False
    timer.deactivate()
    status.set_text("Detection is off.")


async def poll_gamepad(binding_filter: Any, status: Any, state: dict[str, Any], timer: Any) -> None:
    if not state["active"]:
        return
    result = await ui.run_javascript(
        """(() => {
            if (!navigator.getGamepads) return JSON.stringify({available: false, gamepads: []});
            const gamepads = Array.from(navigator.getGamepads())
                .filter(gamepad => gamepad !== null)
                .map(gamepad => ({
                    index: gamepad.index,
                    id: gamepad.id,
                    buttons: Array.from(gamepad.buttons, button => ({
                        pressed: button.pressed,
                        value: button.value
                    })),
                    axes: Array.from(gamepad.axes)
                }));
            return JSON.stringify({available: true, gamepads});
        })()""",
        timeout=1.0,
    )
    if result is None:
        status.set_text("Controller detection is unavailable in this window.")
        return
    try:
        payload = json.loads(result)
        if not payload.get("available"):
            stop_gamepad_detection(timer, state, status)
            status.set_text("This webview does not support gamepad detection.")
            return
        controls = controls_from_gamepads(payload.get("gamepads", []))
    except (TypeError, ValueError, KeyError) as exc:
        _logger.exception("Could not read gamepad state")
        stop_gamepad_detection(timer, state, status)
        status.set_text(f"Controller detection failed: {exc}")
        return
    if controls:
        control = controls[0]
        binding_filter.set_value(control.query)
        refresh_profile()
        stop_gamepad_detection(timer, state, status)
        status.set_text(f"Detected {control.description} on {control.gamepad_id}; filtering by {control.query}.")


async def open_profile_dialog() -> None:
    if app.native.main_window:
        result = await app.native.main_window.create_file_dialog(
            allow_multiple=False,
            file_types=("XML files (*.xml)", "All files (*.*)"),
        )
        if result:
            open_profile(result[0])
            return
    show_path_entry_dialog()


def show_path_entry_dialog() -> None:
    dialog = ui.dialog()
    with dialog:
        with ui.card():
            ui.label("Open XML profile")
            path_input = ui.input("Full XML path").classes("w-full")

            def submit() -> None:
                path = (path_input.value or "").strip()
                if path:
                    open_profile(path)
                    dialog.close()

            ui.button("Open", on_click=submit)
    dialog.open()


def open_profile(path: str | Path) -> None:
    global _current_profile, _profile_browser
    try:
        profile = parse_profile_file(path)
        browser = ProfileBrowser(profile)
        _current_profile = profile
        _profile_browser = browser
        refresh_profile()
    except ProfileParseError as exc:
        ui.notify(str(exc), type="negative")


def clear_filters() -> None:
    state = _profile_ui_state
    if state is None:
        return
    state["binding"].set_value("")
    state["name"].set_value("")
    refresh_profile()


def refresh_profile() -> None:
    state = _profile_ui_state
    browser = _profile_browser
    if state is None or browser is None:
        return
    state["container"].clear()
    binding = state["binding"].value or ""
    name = state["name"].value or ""
    entries = browser.filter(binding_filter=binding, name_filter=name)
    state["count"].set_text(f"{len(entries)} matching binding row(s)")
    if not entries:
        with state["container"]:
            ui.label("No bindings match these filters.").classes("text-grey")
        return
    grouped = browser.grouped_entries(entries)
    filters_active = bool(binding.strip() or name.strip())
    with state["container"]:
        for category, subsections in grouped.items():
            with ui.expansion(category, value=filters_active).classes("w-full"):
                for subsection, subsection_entries in subsections.items():
                    with ui.expansion(subsection, value=filters_active).classes("w-full"):
                        with ui.element("div").classes(
                            "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 w-full p-2"
                        ):
                            for entry in subsection_entries:
                                details = entry.description or "No description available."
                                with ui.card().classes("w-full min-w-0"):
                                    with ui.row().classes("items-center flex-wrap gap-2"):
                                        ui.badge(entry.display_input).props("outline")
                                        action_label = ui.label(entry.action_label).classes("font-medium")
                                        action_label.tooltip(details)
                                        if entry.text_source == "fallback":
                                            ui.badge("Unreviewed").props("color=warning")
                                    ui.label(details).classes("text-body2").props(
                                        'aria-label="Action description"'
                                    )
                                    with ui.expansion("Details").classes("w-full"):
                                        ui.label(f"Action map: {entry.action_map_name or 'Unknown'}")
                                        ui.label(f"Action: {entry.action_name or 'Unknown'}")
                                        ui.label("Raw assignments:")
                                        if entry.all_rebinds:
                                            for raw_input in entry.all_rebinds:
                                                ui.label(raw_input or "(Missing input attribute)").classes(
                                                    "font-mono text-caption"
                                                )
                                        else:
                                            ui.label("(No rebind elements)").classes("font-mono text-caption")


def configure_native_backend() -> None:
    if sys.platform == "linux":
        app.native.start_args["gui"] = "qt"


configure_native_backend()


def run() -> None:
    configure_logging()
    build_ui()
    ui.run(
        native=True,
        host="127.0.0.1",
        window_size=(960, 640),
        title="StarBinder",
        reload=False,
        show=False,
    )


if __name__ == "__main__":
    run()
