"""Qwen3.5 endpoint settings and Russian conversation wording. No model, no Pi, no Mac.

What Pi actually posts (`chat_template_kwargs.enable_thinking`) is decided by Pi from the
models.json this builds. That request, tool calls, and a spoken Russian turn have to be
checked against LM Studio or Ollama on the Mac.
"""
from __future__ import annotations

import json

import pytest

from local_voice.agent_dir import derive_agent_dir
from local_voice.approvals import Approval, heard_answer, ru_question, settings
from local_voice.config import ConfigError, load_config
from local_voice.router import musing, route
from local_voice.ru_lines import line
from local_voice.spaces import load_spaces, pi_space_config
from local_voice.speech_text import yes_no
from local_voice.spoken_cap import wants_more
import yaml


def _spaces_file(tmp_path, spaces, defaults):
    path = tmp_path / "spaces.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "defaults": defaults, "spaces": spaces}))
    return path


def test_shipped_llm_points_at_qwen35_with_thinking_off():
    cfg = load_config()
    assert cfg.llm["model"] == "mlx-community/Qwen3.5-35B-A3B-4bit"
    assert cfg.llm["base_url"] == "http://127.0.0.1:1234/v1"
    assert cfg.llm["context_length"] == 32768
    assert cfg.llm["enable_thinking"] is False
    assert cfg.llm["thinking_format"] == "qwen-chat-template"


def test_a_bad_llm_url_names_the_key():
    with pytest.raises(ConfigError, match="llm.base_url"):
        load_config(overrides={"llm": {"base_url": "localhost:1234"}})


def test_models_json_is_built_from_llm_config_without_a_pi_models_file(tmp_path):
    raw_spaces = {
        "home": {"root": str(tmp_path), "description": "desk", "tools": ["read"], "tier": "ask"},
    }
    path = _spaces_file(tmp_path, raw_spaces, defaults={
        "model": "local/qwen3.5:35b", "deep_model": "local/qwen3.5:35b",
        "thinking": "high", "mode": "conversation", "tier": "ask"})
    cfg = load_config(overrides={
        "pi": {"models_source": str(tmp_path / "missing.json")},
        "agent": {"spaces_file": str(path), "default_space": "home"},
        "llm": {"model": "qwen3.5:35b", "base_url": "http://127.0.0.1:11434/v1",
                "context_length": 16384, "max_tokens": 2048, "enable_thinking": False,
                "name": "Qwen3.5 35B"},
    })
    spaces = load_spaces(cfg, check_paths=False)
    dest = derive_agent_dir(cfg, spaces, tmp_path / "agent")
    provider = json.loads((dest / "models.json").read_text())["providers"]["local"]
    assert provider["baseUrl"] == "http://127.0.0.1:11434/v1"
    assert provider["api"] == "openai-completions"
    model = provider["models"][0]
    assert model["id"] == "qwen3.5:35b"
    assert model["contextWindow"] == 16384 and model["maxTokens"] == 2048
    assert model["reasoning"] is True
    assert model["compat"]["thinkingFormat"] == "qwen-chat-template"
    assert model["compat"]["supportsStrictMode"] is False
    assert model["compat"]["maxTokensField"] == "max_tokens"
    settings = json.loads((dest / "settings.json").read_text())
    assert settings["defaultModel"] == "qwen3.5:35b"
    child = pi_space_config(cfg, spaces["home"], agent_dir=dest, state_dir=tmp_path / "state")
    argv = child.argv()
    assert argv[argv.index("--thinking") + 1] == "off"   # enable_thinking false wins over the space's "high"


def test_thinking_stays_on_when_the_flag_says_so(tmp_path):
    path = _spaces_file(tmp_path, {"home": {"root": str(tmp_path), "description": "desk", "tools": ["read"]}},
                        {"model": "local/qwen3.5:35b", "thinking": "low", "mode": "conversation", "tier": "ask"})
    cfg = load_config(overrides={
        "pi": {"models_source": str(tmp_path / "missing.json")},
        "agent": {"spaces_file": str(path), "default_space": "home"},
        "llm": {"model": "qwen3.5:35b", "base_url": "http://127.0.0.1:1234/v1",
                "context_length": 8192, "enable_thinking": True},
    })
    spaces = load_spaces(cfg, check_paths=False)
    child = pi_space_config(cfg, spaces["home"], agent_dir=tmp_path, state_dir=tmp_path)
    argv = child.argv()
    assert argv[argv.index("--thinking") + 1] == "low"


def test_another_model_still_comes_from_models_json(tmp_path):
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"providers": {"local": {
        "baseUrl": "http://127.0.0.1:9/v1", "api": "openai-completions",
        "models": [{"id": "other", "maxTokens": 100000}]}}}))
    path = _spaces_file(tmp_path, {"home": {"root": str(tmp_path), "description": "desk", "tools": ["read"]}},
                        {"model": "local/other", "thinking": "off", "mode": "conversation", "tier": "ask"})
    cfg = load_config(overrides={
        "pi": {"models_source": str(models)},
        "agent": {"spaces_file": str(path), "default_space": "home"},
        "llm": {"model": "qwen3.5:35b", "base_url": "http://127.0.0.1:1234/v1", "context_length": 8192},
    })
    spaces = load_spaces(cfg, check_paths=False)
    dest = derive_agent_dir(cfg, spaces, tmp_path / "agent", base_url="http://127.0.0.1:1/v1")
    got = json.loads((dest / "models.json").read_text())["providers"]["local"]
    assert {m["id"] for m in got["models"]} == {"other"}
    assert got["models"][0]["maxTokens"] == cfg.pi_max_tokens   # capped, the file said 100000
    assert got["baseUrl"] == "http://127.0.0.1:1/v1"


def test_russian_yes_no_and_a_longer_answer():
    assert yes_no("Да.") is True and yes_no("нет, не надо") is False and yes_no("может быть") is None
    assert yes_no("Yes.") is True
    assert wants_more("расскажи подробнее") and wants_more("tell me more")
    assert not wants_more("что такое тепловой насос")
    offered = ["allow_once", "allow_session", "deny"]
    assert heard_answer("да", offered, "") == "allow_once"
    assert heard_answer("нет", offered, "") == "deny"
    assert heard_answer("да, но назови иначе", offered, "") == "deny_said"
    assert heard_answer("да, на эту сессию", offered, "") == "allow_session"
    assert heard_answer("подожди", offered, "") is None
    assert line("ru", "One moment.", "Секунду.") == "Секунду."
    assert line("en", "One moment.", "Секунду.") == "One moment."


def test_russian_routes_and_a_destructive_question_says_so():
    spaces = load_spaces(load_config(), check_paths=False)
    assert (route("домой", spaces).kind, route("домой", spaces).space) == ("switch", "home")
    assert route("перейди в журнал", spaces).space == "atlas"
    assert route("открой базу знаний", spaces).space == "kb"
    assert route("режим действий", spaces).mode == "act"
    assert route("просто говори", spaces).mode == "conversation"
    assert route("Что такое тепловой насос?", spaces).kind == "none"
    assert musing("Запиши это: сад был тихий") == "сад был тихий"
    approval = Approval(id="1", kind="select", title="", message="rm -rf notes", summary="", short="",
                        action={"tool": "bash", "effect": "delete", "command": "rm -rf notes"},
                        scope=None, options=["allow_once", "deny"])
    said = ru_question(approval)
    assert said.startswith("Запустить команду") and "удаляет файлы" in said
    assert settings(load_config()).for_lang("ru").labels["deny"] == "Не надо"
    assert settings(load_config()).for_lang("en").labels["deny"] == "Don't"
