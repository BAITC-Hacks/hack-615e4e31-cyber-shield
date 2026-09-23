"""Server-only .env loading, without using the developer's real configuration."""

from app import config


def test_local_file_loaded_and_process_key_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("ALEM_LOAD_ENV", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "process-test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=file-test-key\nOPENAI_MODEL=test-model\n")
    config.load_local_env()
    assert config.os.environ["OPENAI_API_KEY"] == "process-test-key"
    assert config.os.environ["OPENAI_MODEL"] == "test-model"


def test_local_file_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("ALEM_LOAD_ENV", "0")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    (tmp_path / ".env").write_text("OPENAI_MODEL=must-not-load\n")
    config.load_local_env()
    assert "OPENAI_MODEL" not in config.os.environ
