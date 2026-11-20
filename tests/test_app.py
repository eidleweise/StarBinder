import unittest
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starbinder import __version__
from starbinder import __main__ as application
from starbinder.profile import (
    ProfileParseError,
    ProfileStore,
    parse_profile_file,
    parse_profile_text,
)
from starbinder.catalog import ActionCatalog
from starbinder.input import normalize_input, parse_input
from starbinder.hardware_input import controls_from_gamepads
from starbinder.presentation import ProfileBrowser
from starbinder.logging_config import configure_logging, get_log_directory


FIXTURES = Path(__file__).resolve().parents[1] / "Documentation" / "mappings"


class ApplicationTests(unittest.TestCase):
    def test_application_version_is_set(self) -> None:
        self.assertEqual(__version__, "0.1.0")

    def test_linux_uses_qt_webview_backend(self) -> None:
        with (
            patch.object(application.sys, "platform", "linux"),
            patch.dict(application.app.native.start_args, {}, clear=True),
        ):
            application.configure_native_backend()
            self.assertEqual(application.app.native.start_args["gui"], "qt")

    def test_windows_uses_default_webview_backend(self) -> None:
        with (
            patch.object(application.sys, "platform", "win32"),
            patch.dict(application.app.native.start_args, {}, clear=True),
        ):
            application.configure_native_backend()
            self.assertNotIn("gui", application.app.native.start_args)

    def test_run_starts_native_ui_on_loopback(self) -> None:
        with (
            patch.object(application, "build_ui") as build_ui,
            patch.object(application.ui, "run") as run_ui,
        ):
            application.run()

        build_ui.assert_called_once_with()
        run_ui.assert_called_once_with(
            native=True,
            host="127.0.0.1",
            window_size=(960, 640),
            title="StarBinder",
            reload=False,
            show=False,
        )


class ProfileParserTests(unittest.TestCase):
    def test_fixture_corpus_parses_metadata_maps_actions_and_rebinds(self) -> None:
        for fixture in sorted(FIXTURES.glob("*.xml")):
            with self.subTest(fixture=fixture.name):
                profile = parse_profile_file(fixture)
                self.assertIsNotNone(profile.profile_name)
                self.assertGreater(len(profile.action_maps), 0)
                self.assertGreater(sum(len(action_map.actions) for action_map in profile.action_maps), 0)

    def test_concrete_assignment_multiple_rebinds_and_repeated_action_names(self) -> None:
        profile = parse_profile_file(FIXTURES / "layout_BenGG470_exported.xml")
        matches = profile.find_action("v_set_mining_mode")
        self.assertEqual(
            [rebind.input for rebind in matches[0].rebinds],
            ["kb1_ralt+m"],
        )

        repeated = [
            (action_map.name, action.name)
            for action_map, action in profile.actions()
            if action.name == "v_set_mining_mode"
        ]
        self.assertGreaterEqual(len(repeated), 1)

        profile = parse_profile_text(
            '<ActionMaps profileName="test">'
            '<actionmap name="one"><action name="same"><rebind input="kb1_a"/><rebind input="js1_button1"/></action></actionmap>'
            '<actionmap name="two"><action name="same"><rebind input="kb1_b"/></action></actionmap>'
            "</ActionMaps>"
        )
        self.assertEqual(len(profile.find_action("same")), 2)
        self.assertEqual(
            [rebind.input for rebind in profile.find_action("same", "one")[0].rebinds],
            ["kb1_a", "js1_button1"],
        )

    def test_missing_rebind_is_distinct_from_whitespace_value(self) -> None:
        profile = parse_profile_text(
            '<ActionMaps><actionmap name="map">'
            '<action name="unbound"><rebind input="kb1_ "/></action>'
            '<action name="no_rebind"/></actionmap></ActionMaps>'
        )
        unbound = profile.find_action("unbound")[0]
        no_rebind = profile.find_action("no_rebind")[0]
        self.assertEqual(unbound.rebinds[0].input, "kb1_ ")
        self.assertEqual(no_rebind.rebinds, [])
        self.assertNotIn("kb1_ ", profile.unknown_tokens)

    def test_unknown_xml_and_tokens_are_preserved_as_warnings(self) -> None:
        profile = parse_profile_text(
            '<ActionMaps futureAttr="kept"><futureNode value="kept"/>'
            '<actionmap name="map" futureMapAttr="kept"><action name="future_action">'
            '<rebind input="future_device_button7" futureRebindAttr="kept"/></action></actionmap></ActionMaps>'
        )
        self.assertIn("future_device_button7", profile.unknown_tokens)
        self.assertTrue(profile.unknown_elements)
        rebind = profile.find_action("future_action")[0].rebinds[0]
        self.assertEqual(rebind.attributes["futureRebindAttr"], "kept")
        self.assertTrue(any(w.code == "unknown_xml_element" for w in profile.warnings))
        self.assertTrue(any(w.code == "unknown_input_token" for w in profile.warnings))

    def test_malformed_input_does_not_replace_open_profile(self) -> None:
        store = ProfileStore(parse_profile_text(
            '<ActionMaps profileName="original"><actionmap name="map"/></ActionMaps>'
        ))
        original = store.current_profile
        with self.assertRaises(ProfileParseError) as context:
            store.open('<ActionMaps><actionmap>')
        self.assertIn("Malformed XML", str(context.exception))
        self.assertIs(store.current_profile, original)


class Story4And5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = parse_profile_text(
            '<ActionMaps profileName="test">'
            '<actionmap name="spaceship_movement">'
            '<action name="v_forward"><rebind input="kb1_space"/></action>'
            '<action name="v_back"><rebind input="kb1_s"/></action>'
            '<action name="v_future_action"><rebind input="future_device_button7"/></action>'
            '</actionmap>'
            '<actionmap name="future_map"><action name="future_action"><rebind input="js2_button3"/></action></actionmap>'
            '</ActionMaps>'
        )
        self.browser = ProfileBrowser(self.profile)

    def test_curated_localized_text_is_resolved_separately(self) -> None:
        catalog = ActionCatalog.load("en-US")
        resolved = catalog.resolve_action("spaceship_movement", "v_forward")
        self.assertEqual(resolved.label, "Move Forward")
        self.assertEqual(resolved.description, "Move the ship or character forward.")
        self.assertTrue(resolved.is_curated)
        self.assertIsNone(resolved.label_key if False else None)

    def test_locale_and_neutral_fallbacks(self) -> None:
        catalog = ActionCatalog(catalog={
            "action_maps": {},
            "actions": {
                "unknown_map": {
                    "v_toggle_qdrive": {
                        "label_key": "action.unknown_map.v_toggle_qdrive-name",
                        "description_key": "action.unknown_map.v_toggle_qdrive-description",
                    }
                }
            },
        }, locales={
            "en-US": {
                "action": {
                    "unknown_map": {
                        "v_toggle_qdrive-name": "Toggle Quantum Drive",
                    }
                }
            }
        })
        exact = catalog.resolve_action("unknown_map", "v_toggle_qdrive")
        self.assertEqual(exact.label, "Toggle Quantum Drive")
        neutral = catalog.resolve_action("unknown_map", "v_new_unknown_action")
        self.assertEqual(neutral.label, "New Unknown Action")
        self.assertTrue(neutral.is_fallback)

    def test_neutral_name_derivation(self) -> None:
        catalog = ActionCatalog.load()
        resolved = catalog.resolve_action("unmapped", "v_ifcs_toggle_qdrive")
        self.assertEqual(resolved.label, "IFCS Toggle Quantum Drive")

    def test_input_formatting_and_placeholder(self) -> None:
        parsed = parse_input("kb1_ralt+m")
        self.assertEqual(parsed.display, "Right Alt + M")
        joystick = parse_input("js2_button3")
        self.assertEqual(joystick.display, "Joystick 2 - Button 3")
        placeholder = parse_input("kb1_ ")
        self.assertFalse(placeholder.is_bound)
        self.assertEqual(placeholder.display, "(No binding)")

    def test_binding_and_name_filters_intersect(self) -> None:
        binding_matches = self.browser.filter(binding_filter="kb1 space")
        self.assertEqual(len(binding_matches), 1)
        self.assertEqual(binding_matches[0].action_name, "v_forward")

        name_matches = self.browser.filter(name_filter="forward")
        self.assertEqual({entry.action_name for entry in name_matches}, {"v_forward"})

        both = self.browser.filter(binding_filter="s", name_filter="backward")
        self.assertEqual(len(both), 1)
        self.assertEqual(both[0].action_name, "v_back")

    def test_joystick_bindings_match_display_and_raw_device_aliases(self) -> None:
        profile = parse_profile_text(
            '<ActionMaps><actionmap name="spaceship_movement">'
            '<action name="one"><rebind input="js1_button3"/></action>'
            '<action name="two"><rebind input="js2_hat1_up"/></action>'
            '<action name="three"><rebind input="js1_rotz"/></action>'
            '</actionmap></ActionMaps>'
        )
        browser = ProfileBrowser(profile)
        expected = {"one", "two", "three"}
        for query in ("joystick", "Joystick 1", "js1", "joy 1", "stick 1"):
            with self.subTest(query=query):
                self.assertEqual(
                    {entry.action_name for entry in browser.filter(binding_filter=query)},
                    expected if query == "joystick" else {"one", "three"},
                )
        self.assertEqual(
            [entry.action_name for entry in browser.filter(binding_filter="stick 2 hat 1 up")],
            ["two"],
        )
        self.assertEqual(
            [entry.action_name for entry in browser.filter(binding_filter="btn3")],
            ["one"],
        )

    def test_hardware_capture_converts_pressed_buttons_and_moved_axes(self) -> None:
        controls = controls_from_gamepads([{
            "index": 0,
            "id": "Test stick",
            "buttons": [
                {"pressed": False, "value": 0.0},
                {"pressed": True, "value": 1.0},
            ],
            "axes": [0.0, -0.75, 0.0, 0.0],
        }])
        self.assertEqual(
            [(control.query, control.control_type) for control in controls],
            [("js1_button2", "button"), ("js1_y", "axis")],
        )
        profile = parse_profile_text(
            '<ActionMaps><actionmap name="spaceship_movement">'
            '<action name="vertical"><rebind input="js1_y"/></action>'
            '<action name="horizontal"><rebind input="js1_x"/></action>'
            '</actionmap></ActionMaps>'
        )
        self.assertEqual(
            [entry.action_name for entry in ProfileBrowser(profile).filter(binding_filter="axis y")],
            ["vertical"],
        )

    def test_hardware_capture_ignores_axis_noise_and_maps_buttons_one_based(self) -> None:
        controls = controls_from_gamepads([{
            "index": 1,
            "id": "Controller",
            "buttons": [{"pressed": False, "value": 0.81}],
            "axes": [0.49],
        }])
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0].query, "js2_button1")

    def test_detected_device_and_button_number_filter_only_matching_joystick(self) -> None:
        profile = parse_profile_text(
            '<ActionMaps><actionmap name="spaceship_movement">'
            '<action name="js1"><rebind input="js1_button11"/></action>'
            '<action name="js2"><rebind input="js2_button11"/></action>'
            '<action name="js1_other_button"><rebind input="js1_button1"/></action>'
            '</actionmap></ActionMaps>'
        )
        browser = ProfileBrowser(profile)
        detected = controls_from_gamepads([{
            "index": 0,
            "id": "Stick",
            "buttons": [{"pressed": False, "value": 0.0}] * 10
                + [{"pressed": True, "value": 1.0}],
            "axes": [],
        }])
        self.assertEqual(detected[0].query, "js1_button11")
        self.assertEqual(
            [entry.action_name for entry in browser.filter(binding_filter=detected[0].query)],
            ["js1"],
        )

    def test_detected_button_search_is_exact_and_excludes_larger_button_numbers(self) -> None:
        profile = parse_profile_text(
            '<ActionMaps><actionmap name="spaceship_movement">'
            '<action name="button_one"><rebind input="js1_button1"/></action>'
            '<action name="button_ten"><rebind input="js1_button10"/></action>'
            '<action name="button_eleven"><rebind input="js2_button11"/></action>'
            '</actionmap></ActionMaps>'
        )
        browser = ProfileBrowser(profile)
        self.assertEqual(
            [entry.action_name for entry in browser.filter(binding_filter="button1")],
            ["button_one"],
        )
        self.assertEqual(
            [entry.action_name for entry in browser.filter(binding_filter="btn 10")],
            ["button_ten"],
        )

    def test_raw_action_input_and_unknown_map_remain_searchable(self) -> None:
        raw = self.browser.filter(name_filter="v_future_action")
        self.assertEqual(len(raw), 1)
        unknown = self.browser.filter(binding_filter="button3")
        self.assertEqual(len(unknown), 1)
        entry = unknown[0]
        self.assertEqual(entry.action_map_label, "Other")
        self.assertEqual(entry.raw_input, "js2_button3")
        self.assertEqual(normalize_input(entry.raw_input), "joystick 2 button 3")

    def test_grouping_builds_category_and_action_map_accordion_levels(self) -> None:
        groups = self.browser.grouped_entries()
        self.assertIn("Flight", groups)
        self.assertIn("Movement", groups["Flight"])
        self.assertIn("Other", groups)
        self.assertIn("future_map", groups["Other"])

    def test_each_binding_entry_exposes_all_ordered_rebinds_for_details(self) -> None:
        profile = parse_profile_text(
            '<ActionMaps><actionmap name="spaceship_movement"><action name="v_forward">'
            '<rebind input="kb1_w"/><rebind input="js1_button2"/>'
            '</action></actionmap></ActionMaps>'
        )
        entries = ProfileBrowser(profile).entries()
        self.assertEqual([entry.raw_input for entry in entries], ["kb1_w", "js1_button2"])
        self.assertEqual(entries[0].all_rebinds, ("kb1_w", "js1_button2"))


class LoggingTests(unittest.TestCase):
    def test_logging_writes_to_dedicated_folder_and_rotates(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            log_directory = Path(temporary_directory) / "starbinder" / "logs"
            returned_directory = configure_logging(log_directory)
            logger = logging.getLogger("starbinder.test")
            handler = next(
                handler
                for handler in logging.getLogger().handlers
                if getattr(handler, "baseFilename", None) == str(log_directory / "starbinder.log")
            )
            try:
                logger.info("test log entry")
                handler.flush()
                self.assertEqual(handler.maxBytes, 5 * 1024 * 1024)
                self.assertEqual(handler.backupCount, 5)
                self.assertEqual(returned_directory, log_directory)
                self.assertIn("test log entry", (log_directory / "starbinder.log").read_text(encoding="utf-8"))
                handler.doRollover()
                self.assertTrue((log_directory / "starbinder.log.1").exists())
            finally:
                logging.getLogger().removeHandler(handler)
                handler.close()


if __name__ == "__main__":
    unittest.main()
