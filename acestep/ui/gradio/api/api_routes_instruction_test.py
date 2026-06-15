"""Tests for per-task instruction resolution in the gradio API release_task handler.

Regression coverage for audio-to-audio tasks (extract/cover/...) which previously
fell back to the text2music instruction and failed.
"""

import unittest

from acestep.constants import TASK_INSTRUCTIONS
from acestep.ui.gradio.api.api_routes import _resolve_task_instruction


class TestResolveTaskInstruction(unittest.TestCase):
    def test_text2music_returns_default(self):
        self.assertEqual(
            _resolve_task_instruction("text2music", None),
            TASK_INSTRUCTIONS["text2music"],
        )

    def test_cover_uses_its_own_instruction(self):
        result = _resolve_task_instruction("cover", None)
        self.assertEqual(result, TASK_INSTRUCTIONS["cover"])
        self.assertNotEqual(result, TASK_INSTRUCTIONS["text2music"])

    def test_extract_with_track_formats_uppercased_track_name(self):
        result = _resolve_task_instruction("extract", "vocals")
        self.assertIn("VOCALS", result)
        self.assertNotIn("{TRACK_NAME}", result)

    def test_extract_without_track_uses_default(self):
        self.assertEqual(
            _resolve_task_instruction("extract", None),
            TASK_INSTRUCTIONS["extract_default"],
        )

    def test_complete_without_classes_uses_default(self):
        self.assertEqual(
            _resolve_task_instruction("complete", None),
            TASK_INSTRUCTIONS["complete_default"],
        )

    def test_unknown_task_falls_back_to_text2music(self):
        self.assertEqual(
            _resolve_task_instruction("nonsense", None),
            TASK_INSTRUCTIONS["text2music"],
        )


if __name__ == "__main__":
    unittest.main()
