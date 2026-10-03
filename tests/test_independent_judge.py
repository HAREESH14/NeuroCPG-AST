"""Tests for scripts/resubmission_independent_judge.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import functions from scripts/resubmission_independent_judge.py
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import resubmission_independent_judge as judge_script


class TestSafeModelName:
    def test_safe_model_name_slashes_and_colons(self) -> None:
        assert (
            judge_script._safe_model_name("nvidia_nim/meta/llama-3.3-70b-instruct")
            == "nvidia_nim_meta_llama-3.3-70b-instruct"
        )
        assert judge_script._safe_model_name("ollama/llama3.1:8b") == "ollama_llama3.1_8b"
        assert judge_script._safe_model_name("ollama/qwen2.5-coder:7b") == "ollama_qwen2.5-coder_7b"


class TestClassify:
    def test_parse_error(self) -> None:
        assert judge_script._classify(1, -1) == "PARSE_ERROR"
        assert judge_script._classify(0, -1) == "PARSE_ERROR"

    def test_agree_flagged(self) -> None:
        assert judge_script._classify(2, 1) == "AGREE_FLAGGED"

    def test_judge_missed(self) -> None:
        assert judge_script._classify(2, 0) == "JUDGE_MISSED"

    def test_judge_false_alarm(self) -> None:
        assert judge_script._classify(0, 1) == "JUDGE_FALSE_ALARM"

    def test_agree_clean(self) -> None:
        assert judge_script._classify(0, 0) == "AGREE_CLEAN"


class TestExtractJson:
    def test_direct_json(self) -> None:
        raw = '{"hallucinations_found": 2, "is_equivalent": false, "explanation": "test"}'
        parsed = judge_script._extract_json(raw)
        assert parsed["hallucinations_found"] == 2

    def test_markdown_fenced_json(self) -> None:
        raw = (
            '```json\n{"hallucinations_found": 0, "is_equivalent": true, "explanation": "ok"}\n```'
        )
        parsed = judge_script._extract_json(raw)
        assert parsed["hallucinations_found"] == 0
        assert parsed["is_equivalent"] is True

    def test_embedded_braces(self) -> None:
        raw = (
            "Here is my analysis:\n"
            '{"hallucinations_found": 1, "is_equivalent": false, "explanation": "bad"}\n'
            "Done."
        )
        parsed = judge_script._extract_json(raw)
        assert parsed["hallucinations_found"] == 1

    def test_parse_failure(self) -> None:
        raw = "Not a valid json response at all."
        parsed = judge_script._extract_json(raw)
        assert parsed.get("_parse_failed") is True


class TestJudgeTranslation:
    @patch("resubmission_independent_judge.litellm.completion")
    def test_judge_translation_nvidia_nim(self, mock_completion: MagicMock) -> None:
        json_resp = '{"hallucinations_found": 3, "is_equivalent": false, "explanation": "Missing"}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_completion.return_value = mock_response

        report = judge_script.judge_translation(
            c_code="int main() { return 0; }",
            java_code="class Main {}",
            judge_model="nvidia_nim/meta/llama-3.3-70b-instruct",
            nvidia_url="https://integrate.api.nvidia.com/v1",
            nvidia_key="test-nv-key",
        )

        assert report["hallucinations_found"] == 3
        assert report["is_equivalent"] is False
        mock_completion.assert_called_once()
        kwargs = mock_completion.call_args[1]
        assert kwargs["model"] == "nvidia_nim/meta/llama-3.3-70b-instruct"
        assert kwargs["api_base"] == "https://integrate.api.nvidia.com/v1"
        assert kwargs["api_key"] == "test-nv-key"

    @patch("resubmission_independent_judge.litellm.completion")
    def test_judge_translation_ollama(self, mock_completion: MagicMock) -> None:
        json_resp = '{"hallucinations_found": 0, "is_equivalent": true, "explanation": "Match"}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_completion.return_value = mock_response

        report = judge_script.judge_translation(
            c_code="int main() { return 0; }",
            java_code="class Main {}",
            judge_model="llama3.1:8b",
            ollama_url="https://test-colab.ngrok-free.dev",
        )

        assert report["hallucinations_found"] == 0
        assert report["is_equivalent"] is True
        mock_completion.assert_called_once()
        kwargs = mock_completion.call_args[1]
        assert kwargs["model"] == "ollama/llama3.1:8b"
        assert kwargs["api_base"] == "https://test-colab.ngrok-free.dev"


class TestMainValidation:
    def test_main_rejects_url_as_nvidia_key(self) -> None:
        test_args = [
            "resubmission_independent_judge.py",
            "--nvidia-key",
            "https://integrate.api.nvidia.com/v1",
        ]
        with (
            patch.object(sys, "argv", test_args),
            pytest.raises(ValueError, match="You passed a URL"),
        ):
            judge_script.main()
