import sys

from nicegui import app, ui


def build_ui() -> None:
    with ui.column().classes("w-full items-center gap-4 p-8"):
        ui.label("StarBinder").classes("text-h4")
        ui.label("Application skeleton is running.")


def configure_native_backend() -> None:
    if sys.platform == "linux":
        app.native.start_args["gui"] = "qt"


configure_native_backend()


def run() -> None:
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
