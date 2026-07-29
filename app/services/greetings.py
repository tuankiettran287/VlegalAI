from __future__ import annotations

import re
import unicodedata


_GREETING_LANGUAGES = {
    # Vietnamese
    "xin chào": "vi",
    "xin chao": "vi",
    "chào": "vi",
    "chao": "vi",
    "chào bạn": "vi",
    "chao ban": "vi",
    "chào buổi sáng": "vi",
    "chao buoi sang": "vi",
    "chào buổi chiều": "vi",
    "chao buoi chieu": "vi",
    "chào buổi tối": "vi",
    "chao buoi toi": "vi",
    "alo": "vi",
    # English
    "hi": "en",
    "hello": "en",
    "hey": "en",
    "greetings": "en",
    "good morning": "en",
    "good afternoon": "en",
    "good evening": "en",
    "good night": "en",
    # French
    "bonjour": "fr",
    "bonsoir": "fr",
    "salut": "fr",
    # Spanish
    "hola": "es",
    "buenos días": "es",
    "buenas tardes": "es",
    "buenas noches": "es",
    # German
    "hallo": "de",
    "guten tag": "de",
    "guten morgen": "de",
    # Italian
    "ciao": "it",
    "buongiorno": "it",
    "buonasera": "it",
    # Portuguese
    "olá": "pt",
    "oi": "pt",
    "bom dia": "pt",
    "boa tarde": "pt",
    "boa noite": "pt",
    # Chinese, Japanese, Korean and Thai
    "你好": "zh",
    "您好": "zh",
    "早上好": "zh",
    "晚上好": "zh",
    "こんにちは": "ja",
    "おはよう": "ja",
    "こんばんは": "ja",
    "안녕하세요": "ko",
    "안녕": "ko",
    "สวัสดี": "th",
    # Other common greetings
    "halo": "id",
    "selamat pagi": "id",
    "selamat siang": "id",
    "selamat sore": "id",
    "selamat malam": "id",
    "привет": "ru",
    "здравствуйте": "ru",
    "مرحبا": "ar",
    "أهلا": "ar",
    "السلام عليكم": "ar",
    "नमस्ते": "hi",
    "नमस्कार": "hi",
    "merhaba": "tr",
    "kamusta": "fil",
    "γεια": "el",
    "γεια σου": "el",
    "cześć": "pl",
    "ahoj": "cs",
    "hej": "sv",
    "hei": "no",
    "שלום": "he",
}

_ALLOWED_ADDRESSEES = {
    "ai",
    "all",
    "assistant",
    "bạn",
    "ban",
    "everyone",
    "mọi người",
    "moi nguoi",
    "there",
    "vlegal",
    "vlegal ai",
}

_GREETING_RESPONSES = {
    "vi": (
        "Chào {name}! Mình là VLegal AI. Mình có thể giúp bạn tra cứu quy "
        "định, phân tích tình huống hoặc giải thích quyền và nghĩa vụ pháp "
        "lý. Bạn muốn hỏi vấn đề gì?"
    ),
    "en": (
        "Hello {name}! I'm VLegal AI. I can help you look up legal rules, "
        "analyze a situation, or understand legal rights and obligations. "
        "What would you like to ask?"
    ),
    "fr": (
        "Bonjour {name} ! Je suis VLegal AI. Quelle question juridique "
        "souhaitez-vous examiner ?"
    ),
    "es": (
        "¡Hola, {name}! Soy VLegal AI. ¿Qué cuestión jurídica te gustaría "
        "consultar?"
    ),
    "de": (
        "Hallo {name}! Ich bin VLegal AI. Bei welcher rechtlichen Frage "
        "kann ich helfen?"
    ),
    "it": (
        "Ciao {name}! Sono VLegal AI. Quale questione legale vuoi "
        "approfondire?"
    ),
    "pt": (
        "Olá, {name}! Sou o VLegal AI. Que questão jurídica você gostaria "
        "de analisar?"
    ),
    "zh": "你好，{name}！我是 VLegal AI。你想咨询什么法律问题？",
    "ja": (
        "こんにちは、{name}さん！VLegal AIです。どのような法律問題について"
        "相談したいですか？"
    ),
    "ko": "안녕하세요, {name}님! VLegal AI입니다. 어떤 법률 문제가 궁금하신가요?",
    "th": (
        "สวัสดี {name}! ฉันคือ VLegal AI คุณต้องการสอบถามปัญหากฎหมายเรื่องใด?"
    ),
    "id": (
        "Halo {name}! Saya VLegal AI. Masalah hukum apa yang ingin Anda "
        "tanyakan?"
    ),
    "ru": (
        "Здравствуйте, {name}! Я VLegal AI. Какой юридический вопрос вы "
        "хотите обсудить?"
    ),
    "ar": "مرحبًا {name}! أنا VLegal AI. ما المسألة القانونية التي تود السؤال عنها؟",
    "hi": (
        "नमस्ते {name}! मैं VLegal AI हूँ। आप किस कानूनी विषय के बारे में "
        "पूछना चाहते हैं?"
    ),
    "tr": (
        "Merhaba {name}! Ben VLegal AI. Hangi hukuki konuda yardımcı "
        "olabilirim?"
    ),
    "fil": (
        "Kumusta {name}! Ako si VLegal AI. Anong legal na usapin ang nais "
        "mong itanong?"
    ),
    "el": (
        "Γεια σου, {name}! Είμαι το VLegal AI. Ποιο νομικό ζήτημα θα ήθελες "
        "να εξετάσουμε;"
    ),
    "pl": (
        "Cześć {name}! Jestem VLegal AI. W jakiej sprawie prawnej mogę "
        "pomóc?"
    ),
    "cs": (
        "Ahoj {name}! Jsem VLegal AI. S jakou právní otázkou mohu pomoci?"
    ),
    "sv": (
        "Hej {name}! Jag är VLegal AI. Vilken juridisk fråga vill du ha "
        "hjälp med?"
    ),
    "no": (
        "Hei {name}! Jeg er VLegal AI. Hvilket juridisk spørsmål kan jeg "
        "hjelpe deg med?"
    ),
    "he": "שלום {name}! אני VLegal AI. באיזו שאלה משפטית אפשר לעזור?",
}


def _normalize_greeting(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    cleaned = "".join(
        " " if unicodedata.category(character)[0] in {"P", "S"} else character
        for character in normalized
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def detect_greeting_language(value: str) -> str | None:
    """Recognize a standalone social greeting without swallowing a question."""

    normalized = _normalize_greeting(value)
    if not normalized:
        return None
    direct = _GREETING_LANGUAGES.get(normalized)
    if direct:
        return direct

    for addressee in _ALLOWED_ADDRESSEES:
        suffix = f" {addressee}"
        if not normalized.endswith(suffix):
            continue
        greeting = normalized[: -len(suffix)].strip()
        language = _GREETING_LANGUAGES.get(greeting)
        if language:
            return language
    return None


def greeting_response(value: str, preferred_name: str) -> str | None:
    language = detect_greeting_language(value)
    if language is None:
        return None
    template = _GREETING_RESPONSES.get(language, _GREETING_RESPONSES["en"])
    return template.format(name=preferred_name.strip() or "bạn")


__all__ = ["detect_greeting_language", "greeting_response"]
