from app.core.config import Settings


def test_settings_parse_json_array_origins() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins='["http://localhost:5173", "http://127.0.0.1:5173"]',
    )

    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_settings_parse_csv_origins() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="http://localhost:5173,http://127.0.0.1:5173",
    )

    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
