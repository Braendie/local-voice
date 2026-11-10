"""Selecting an llm preset without touching the shipped 35B default. No model server, no Mac."""
from __future__ import annotations

import json

from local_voice.agent_dir import derive_agent_dir
from local_voice.config import ConfigError, load_config
from local_voice.spaces import load_spaces, persona_text, pi_space_config

import pytest

NINE = {
    "provider": "local",
    "model": "qwen3.5:9b-q5_K_M",
    "name": "Qwen3.5-9B Q5_K_M",
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "context_length": 16384,
    "max_tokens": 2048,
    "enable_thinking": False,
    "thinking_format": "qwen-chat-template",
    "prompt_extra": "Keep every spoken reply to one short sentence. Call tools only through the tool interface.",
}


def test_the_default_stays_the_35b_studio_model():
    cfg = load_config()
    assert cfg.llm["preset"] is None
    assert cfg.llm["model"] == "mlx-community/Qwen3.5-35B-A3B-4bit"
    assert cfg.llm["base_url"] == "http://127.0.0.1:1234/v1"
    assert cfg.llm["context_length"] == 32768
    assert cfg.llm["prompt_extra"] == ""


def test_a_preset_replaces_the_endpoint_and_ignores_the_35b_id(tmp_path):
    path = tmp_path / "spaces.yaml"
    path.write_text(
        "version: 1\n"
        "defaults:\n"
        "  model: local/mlx-community/Qwen3.5-35B-A3B-4bit\n"
        "  deep_model: local/mlx-community/Qwen3.5-35B-A3B-4bit\n"
        "  thinking: high\n"
        "  mode: conversation\n"
        "  tier: ask\n"
        "spaces:\n"
        "  home:\n"
        "    root: .\n"
        "    description: desk\n"
        "    tools: [read]\n")
    cfg = load_config(overrides={
        "pi": {"models_source": str(tmp_path / "missing.json")},
        "agent": {"spaces_file": str(path), "default_space": "home"},
        "llm": {"preset": "qwen35-9b-q5"},
        "llm_presets": {"qwen35-9b-q5": dict(NINE)},
    })
    assert cfg.llm["model"] == "qwen3.5:9b-q5_K_M"
    assert cfg.llm["base_url"] == "http://127.0.0.1:11434/v1"
    assert cfg.llm["context_length"] == 16384
    assert cfg.llm["max_tokens"] == 2048
    assert cfg.llm["enable_thinking"] is False
    assert cfg.llm["thinking_format"] == "qwen-chat-template"
    spaces = load_spaces(cfg, check_paths=False)
    dest = derive_agent_dir(cfg, spaces, tmp_path / "agent")
    provider = json.loads((dest / "models.json").read_text())["providers"]["local"]
    assert provider["baseUrl"] == "http://127.0.0.1:11434/v1"
    assert [m["id"] for m in provider["models"]] == ["qwen3.5:9b-q5_K_M"]
    assert provider["models"][0]["contextWindow"] == 16384
    assert provider["models"][0]["maxTokens"] == 2048
    assert provider["models"][0]["compat"]["thinkingFormat"] == "qwen-chat-template"
    settings = json.loads((dest / "settings.json").read_text())
    assert settings["defaultModel"] == "qwen3.5:9b-q5_K_M"
    child = pi_space_config(cfg, spaces["home"], agent_dir=dest, state_dir=tmp_path / "state")
    argv = child.argv()
    assert argv[argv.index("--model") + 1] == "local/qwen3.5:9b-q5_K_M"
    assert argv[argv.index("--thinking") + 1] == "off"
    prompt = argv[argv.index("--system-prompt") + 1]
    assert prompt.startswith("You are the user's voice assistant")
    assert "one short sentence" in prompt and "tool interface" in prompt


def test_a_local_tag_override_wins_inside_the_preset(tmp_path):
    cfg = load_config(overrides={
        "llm": {"preset": "qwen35-9b-q5"},
        "llm_presets": {"qwen35-9b-q5": {
            **NINE, "model": "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M", "context_length": 32768}},
    })
    assert cfg.llm["model"] == "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M"
    assert cfg.llm["context_length"] == 32768
    assert cfg.llm["base_url"] == "http://127.0.0.1:11434/v1"


def test_the_shipped_9b_preset_is_ollama_q5_and_a_local_tag_can_replace_it():
    cfg = load_config(overrides={"llm": {"preset": "qwen35-9b-q5"}})
    assert cfg.llm["preset"] == "qwen35-9b-q5"
    assert cfg.llm["model"] == "qwen3.5:9b-q5_K_M"
    assert cfg.llm["base_url"] == "http://127.0.0.1:11434/v1"
    assert cfg.llm["context_length"] == 16384
    assert cfg.llm["max_tokens"] == 2048
    assert cfg.llm["enable_thinking"] is False
    assert cfg.llm["thinking_format"] == "qwen-chat-template"
    assert "tool interface" in cfg.llm["prompt_extra"]
    # The 35B block in the same file must not leak into the selected preset.
    assert "35B" not in cfg.llm["model"]
    alt = load_config(overrides={
        "llm": {"preset": "qwen35-9b-q5"},
        "llm_presets": {"qwen35-9b-q5": {"model": "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M"}},
    })
    assert alt.llm["model"] == "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M"
    assert alt.llm["context_length"] == 16384 and alt.llm["base_url"] == "http://127.0.0.1:11434/v1"


def test_an_unknown_preset_names_the_key():
    with pytest.raises(ConfigError, match="llm.preset"):
        load_config(overrides={"llm": {"preset": "no-such"}, "llm_presets": {}})
