import unittest
from unittest.mock import patch

from starbinder import __version__
from starbinder import __main__ as application


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


if __name__ == "__main__":
    unittest.main()
