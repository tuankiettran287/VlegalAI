from __future__ import annotations

import pytest

from app.services.greetings import (
    detect_greeting_language,
    greeting_response,
)


@pytest.mark.parametrize(
    ("message", "language"),
    [
        ("Hi", "en"),
        ("HELLO!!! 👋", "en"),
        ("Hey VLegal AI", "en"),
        ("Xin chào", "vi"),
        ("xin chao ban", "vi"),
        ("Bonjour", "fr"),
        ("¡Hola!", "es"),
        ("你好", "zh"),
        ("こんにちは", "ja"),
        ("안녕하세요", "ko"),
        ("สวัสดี", "th"),
        ("Привет", "ru"),
        ("السلام عليكم", "ar"),
        ("नमस्ते", "hi"),
        ("Γεια σου", "el"),
        ("שלום", "he"),
    ],
)
def test_detects_standalone_multilingual_greetings(
    message: str,
    language: str,
) -> None:
    assert detect_greeting_language(message) == language


@pytest.mark.parametrize(
    "message",
    [
        "Hello, tôi muốn hỏi về quyền nghỉ việc",
        "Xin chào, mức lương tối thiểu hiện nay là bao nhiêu?",
        "Chào bán cổ phiếu cần điều kiện gì?",
        "Hiểu thế nào về cưỡng bức lao động?",
        "Good morning, can an employee refuse dangerous work?",
    ],
)
def test_greeting_detection_does_not_swallow_a_legal_question(
    message: str,
) -> None:
    assert detect_greeting_language(message) is None


def test_greeting_response_is_personalized_and_language_aware() -> None:
    english = greeting_response("Hi", "Khoa")
    vietnamese = greeting_response("Xin chào", "Khoa")
    chinese = greeting_response("你好", "Khoa")

    assert english is not None and english.startswith("Hello Khoa!")
    assert vietnamese is not None and vietnamese.startswith("Chào Khoa!")
    assert chinese is not None and "Khoa" in chinese
