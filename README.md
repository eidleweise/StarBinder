# StarBinder

A desktop application for understanding Star Citizen key bindings.

## Development

Requires [`uv`](https://docs.astral.sh/uv/). The project supports Python
3.11–3.15; `uv` can install the requested interpreter if needed.

```sh
uv sync --locked
uv run --locked python -m starbinder
```

On Linux, native mode uses pywebview with Qt WebEngine. This currently has a
substantial dependency download; native prerequisites may vary by distribution.
On Windows, native mode uses Microsoft Edge WebView2.

Run the local automated tests with:

```sh
uv run --locked python -m unittest discover -s tests -v
```
