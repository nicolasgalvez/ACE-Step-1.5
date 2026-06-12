"""Tests for the clean gradio MCP tool (songscribe_mcp). ACE-Step is mocked."""

import json
import unittest
from unittest.mock import patch

import gradio as gr

from acestep.ui.gradio import songscribe_mcp


class TestAudioPathFromItem(unittest.TestCase):
    def test_parses_result_json_string(self):
        item = {"result": json.dumps([{"file": "/o/x.mp3"}])}
        self.assertEqual(songscribe_mcp._audio_path_from_item(item), "/o/x.mp3")

    def test_handles_list_and_none(self):
        self.assertEqual(songscribe_mcp._audio_path_from_item({"audio_paths": ["/a.wav"]}), "/a.wav")
        self.assertIsNone(songscribe_mcp._audio_path_from_item({"status": 1}))


class TestGenerateSong(unittest.TestCase):
    def test_builds_text2music_body_and_returns_filedata(self):
        calls = {}

        def fake_post(path, body, timeout):
            calls[path] = body
            if path == "/release_task":
                return {"data": {"task_id": "t1"}}
            return {"data": [{"result": json.dumps([{"file": "/out/song.mp3"}])}]}

        with patch.object(songscribe_mcp, "_post", fake_post), patch.object(
            songscribe_mcp, "_download", lambda p, f: "/tmp/local.mp3"
        ), patch.object(songscribe_mcp.time, "sleep", lambda *a: None):
            result = songscribe_mcp.generate_song("dark synthwave", "[inst]", 10, "mp3")

        self.assertEqual(calls["/release_task"]["task_type"], "text2music")
        self.assertEqual(calls["/release_task"]["prompt"], "dark synthwave")
        self.assertEqual(result.path, "/tmp/local.mp3")
        self.assertEqual(result.mime_type, "audio/mpeg")

    def test_invalid_format_raises(self):
        with self.assertRaises(gr.Error):
            songscribe_mcp.generate_song("x", "[inst]", 10, "flac")


class TestRegisterCleanMcpTool(unittest.TestCase):
    def test_adds_one_tool_and_hides_the_rest(self):
        with gr.Blocks() as demo:
            button = gr.Button()
            textbox = gr.Textbox()
            button.click(lambda: 1, outputs=textbox, api_name="noise_fn")

        songscribe_mcp.register_clean_mcp_tool(demo)

        api_names = [getattr(fn, "api_name", None) for fn in demo.fns.values()]
        self.assertIn("generate_song", api_names)
        self.assertNotIn("noise_fn", api_names)


if __name__ == "__main__":
    unittest.main()
