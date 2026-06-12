"""Expose ONE clean, well-typed MCP tool (`generate_song`) on the gradio app.

With ``GRADIO_MCP_SERVER=True`` gradio turns every UI event into an MCP tool —
164 of them, with the real generate as a 72-positional-arg ``generation_wrapper``,
which is unusable for an LLM. ``register_clean_mcp_tool`` adds a single typed
``generate_song`` (via ``gr.api``) and hides the rest from the API/MCP, so a
client sees exactly one drivable tool. Generation reuses this server's own
``/release_task`` REST endpoint, so there is no duplicated generation logic.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

import gradio as gr
from gradio.data_classes import FileData
from loguru import logger

_BASE = f"http://127.0.0.1:{os.environ.get('GRADIO_PORT', '7860')}"
_RENDER_TIMEOUT_S = float(os.environ.get("ACESTEP_RENDER_TIMEOUT", "1800"))
_POLL_TRIES = int(os.environ.get("ACESTEP_POLL_MAX", "600"))
_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav"}


def _post(path: str, body: dict, timeout: float) -> dict:
    """POST JSON to a local server route and return the decoded JSON response."""
    req = urllib.request.Request(
        _BASE + path,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _audio_path_from_item(item: dict) -> Optional[str]:
    """Pull the first audio path out of a /query_result item (shape varies)."""
    for key in ("audio_paths", "result", "audios"):
        value = item.get(key)
        if isinstance(value, str) and value[:1] in "[{":
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        if isinstance(value, list) and value:
            first = value[0]
            path = (
                (first.get("file") or first.get("audio_path") or first.get("path") or first.get("url"))
                if isinstance(first, dict)
                else (first if isinstance(first, str) else None)
            )
            if path:
                return path
        elif isinstance(value, str) and value:
            return value
    return None


def _download(acestep_path: str, audio_format: str) -> str:
    """Download a generated file from /v1/audio to a local temp file; return its path."""
    if acestep_path.startswith("/v1/audio?path="):
        query = urllib.parse.urlparse(acestep_path).query
        acestep_path = urllib.parse.parse_qs(query).get("path", [acestep_path])[0]
    url = f"{_BASE}/v1/audio?path={urllib.parse.quote(acestep_path)}"
    with urllib.request.urlopen(url, timeout=180) as response:
        data = response.read()
    fd, local = tempfile.mkstemp(suffix=f".{audio_format}", prefix="acestep_mcp_")
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return local


def generate_song(
    caption: str,
    lyrics: str = "[inst]",
    audio_duration: float = 30.0,
    audio_format: str = "mp3",
) -> FileData:
    """Generate a song from a style caption and lyrics using ACE-Step.

    Args:
        caption: Style/genre prompt, e.g. "dark synthwave, analog bass, cinematic".
        lyrics: Lyrics, optionally with [verse]/[chorus] tags. "[inst]" for instrumental.
        audio_duration: Length of the track in seconds (default 30).
        audio_format: Output format, "mp3" (default) or "wav".

    Returns:
        The generated audio file.
    """
    fmt = (audio_format or "mp3").lower()
    if fmt not in _MIME:
        raise gr.Error(f"audio_format must be 'mp3' or 'wav'; got {audio_format!r}")
    body = {
        "task_type": "text2music",
        "prompt": caption,
        "lyrics": (lyrics or "").strip() or "[inst]",
        "audio_duration": audio_duration,
        "audio_format": fmt,
        "batch_size": 1,
    }
    submit = _post("/release_task", body, _RENDER_TIMEOUT_S)
    task_id = (submit.get("data") or {}).get("task_id")
    if not task_id:
        raise gr.Error("ACE-Step returned no task_id")

    for _ in range(_POLL_TRIES):
        result = _post("/query_result", {"task_id_list": json.dumps([task_id])}, 30)
        items = result.get("data") or []
        if items:
            path = _audio_path_from_item(items[0])
            if path:
                return FileData(path=_download(path, fmt), mime_type=_MIME[fmt])
            if str(items[0].get("status")) in ("3", "-1"):
                raise gr.Error("ACE-Step generation failed")
        time.sleep(2)
    raise gr.Error("ACE-Step generation timed out")


def register_clean_mcp_tool(demo: Any) -> None:
    """Add `generate_song` to an existing Blocks and hide other functions from MCP.

    A function is exposed in gradio's API/MCP iff its ``api_name`` is truthy;
    setting it to ``False`` hides it (UI events still dispatch by index). This
    leaves exactly one drivable MCP tool.

    Args:
        demo: The gradio ``Blocks`` instance to augment.
    """
    with demo:
        gr.api(generate_song, api_name="generate_song")

    hidden = 0
    fns = getattr(demo, "fns", {})
    for fn in (fns.values() if isinstance(fns, dict) else fns):
        if getattr(fn, "api_name", None) not in ("generate_song", False, None):
            fn.api_name = False
            hidden += 1
    logger.info(f"Registered MCP tool 'generate_song'; hid {hidden} other functions")
