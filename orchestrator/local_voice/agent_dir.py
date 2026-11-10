"""The Pi agent dir the voice children run with.

"derived" (the default) writes one under the state dir at every start. The model Pi calls is
`llm` in config.yaml when that section names it (base URL, context length, and the Qwen
chat-template switch that sends ``chat_template_kwargs.enable_thinking``). Any other model a
space still names is copied from ``pi.models_source`` (read only), as before. Nothing is
written under ~/.pi/agent.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Config, ConfigError
from .spaces import Spaces

GLOBAL_SKILLS = Path("~/.pi/agent/skills").expanduser()


def models_in_use(spaces: Spaces) -> set[tuple[str, str]]:
    out = set()
    for ref in [spaces.defaults.get("model"), spaces.defaults.get("deep_model"), *[s.model for s in spaces.spaces.values()]]:
        if ref and "/" in str(ref):
            prov, _, mid = str(ref).partition("/")
            out.add((prov, mid))
    return out


def llm_model_entry(llm: dict, max_tokens: int) -> dict:
    """One models.json model. ``reasoning`` stays on so Pi sends an explicit thinking switch.

    Qwen3.5 thinks unless the request says otherwise. With ``thinkingFormat``
    ``qwen-chat-template`` and the space's thinking level ``off``, Pi sends
    ``chat_template_kwargs.enable_thinking=false`` (and ``preserve_thinking``). That is the
    low-latency path. The body itself is built by Pi; this entry is what tells it to.
    """
    return {
        "id": llm["model"],
        "name": llm["name"],
        "reasoning": True,
        "input": ["text"],
        "contextWindow": int(llm["context_length"]),
        "maxTokens": min(int(llm["max_tokens"]), max_tokens),
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "compat": {
            "supportsStore": False,
            "supportsDeveloperRole": False,
            "supportsReasoningEffort": False,
            "supportsUsageInStreaming": True,
            "maxTokensField": "max_tokens",
            "supportsStrictMode": False,
            "thinkingFormat": llm["thinking_format"],
        },
    }


def _provider(providers: dict, prov: str, src: dict | None) -> dict:
    if prov in providers:
        return providers[prov]
    src_p = ((src or {}).get("providers") or {}).get(prov) or {}
    entry = {k: v for k, v in src_p.items() if k != "models"}
    entry.setdefault("api", "openai-completions")
    entry["models"] = []
    providers[prov] = entry
    return entry


def derive_agent_dir(cfg: Config, spaces: Spaces, dest: Path, *, base_url: str | None = None) -> Path:
    """Write <dest>/models.json and settings.json; returns dest. base_url overrides the provider's (tests: a stub)."""
    llm = cfg.llm
    src = None
    if cfg.pi_models_source.exists():
        try:
            src = json.loads(cfg.pi_models_source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigError(f"pi.models_source {cfg.pi_models_source} is not valid JSON: {e}") from e
    elif llm is None:
        raise ConfigError(f"pi.models_source {cfg.pi_models_source} does not exist")
    wanted = models_in_use(spaces)
    providers: dict[str, dict] = {}
    for prov, mid in sorted(wanted):
        if llm and prov == llm["provider"] and mid == llm["model"]:
            entry = _provider(providers, prov, src)
            entry["baseUrl"] = base_url or llm["base_url"]
            entry["apiKey"] = llm["api_key"]
            model = llm_model_entry(llm, cfg.pi_max_tokens)
            if not any(m.get("id") == model["id"] for m in entry["models"]):
                entry["models"].append(model)
            continue
        if src is None:
            raise ConfigError(
                f"spaces.yaml names {prov}/{mid}, but {cfg.pi_models_source} does not exist "
                f"and llm.model is {llm['model'] if llm else 'unset'}")
        p = (src.get("providers") or {}).get(prov)
        if p is None:
            raise ConfigError(f"spaces.yaml names {prov}/{mid}, but {cfg.pi_models_source} has no provider {prov!r}")
        entry = _provider(providers, prov, src)
        if base_url:
            entry["baseUrl"] = base_url
        elif "baseUrl" not in entry and p.get("baseUrl"):
            entry["baseUrl"] = p["baseUrl"]
        m = next((x for x in p.get("models") or [] if x.get("id") == mid), None)
        if m is None:
            raise ConfigError(f"spaces.yaml names {prov}/{mid}, which {cfg.pi_models_source} does not list")
        m = dict(m)
        m["maxTokens"] = min(int(m.get("maxTokens") or cfg.pi_max_tokens), cfg.pi_max_tokens)
        if not any(x.get("id") == m["id"] for x in entry["models"]):
            entry["models"].append(m)
    default = str(spaces.defaults.get("model", "local/qwen38")).partition("/")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "models.json").write_text(json.dumps({"providers": providers}, indent=1) + "\n", encoding="utf-8")
    (dest / "settings.json").write_text(json.dumps({"defaultProvider": default[0], "defaultModel": default[2],
                                                    "packages": []}, indent=1) + "\n", encoding="utf-8")
    link = dest / "skills"
    if GLOBAL_SKILLS.is_dir() and not link.exists() and not link.is_symlink():
        os.symlink(GLOBAL_SKILLS, link)
    return dest


def agent_dir_for(cfg: Config, spaces: Spaces, state_dir: Path, *, base_url: str | None = None) -> Path:
    if cfg.pi_agent_dir == "derived":
        return derive_agent_dir(cfg, spaces, state_dir / "pi-agent", base_url=base_url)
    p = Path(cfg.pi_agent_dir).expanduser()
    if not (p / "models.json").exists():
        raise ConfigError(f"pi.agent_dir {p} has no models.json")
    return p
