from pathlib import Path


STATIC_DIR = Path("src/insurance_coach_agents/web_static")


def test_upload_file_input_covers_dropzone() -> None:
    css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

    assert ".dropzone {" in css
    dropzone_block = css.split(".dropzone {", 1)[1].split("}", 1)[0]
    input_block = css.split(".dropzone input {", 1)[1].split("}", 1)[0]

    assert "position: relative;" in dropzone_block
    assert "overflow: hidden;" in dropzone_block
    assert "inset: 0;" in input_block
    assert "width: 100%;" in input_block
    assert "height: 100%;" in input_block
    assert "cursor: pointer;" in input_block


def test_api_fetches_skip_ngrok_browser_warning() -> None:
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert '"ngrok-skip-browser-warning": "true"' in js
    assert 'apiFetch(`/api/tasks/${taskId}/files`)' in js
    assert "apiFetch(`/api/tasks/${taskId}`)" in js
    assert 'apiFetch("/api/tasks", { method: "POST", body: data })' in js
