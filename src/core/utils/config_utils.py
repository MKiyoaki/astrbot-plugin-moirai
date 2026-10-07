"""Hydra 配置（插件根目录的 configs/）：给工具组合配置，并给开发脚本一份与旧 run_config.py 同名的扁平设置。"""
from __future__ import annotations

import os
import shlex
import struct
from types import SimpleNamespace
from typing import Any, Sequence

from omegaconf import DictConfig, OmegaConf

from .paths import PLUGIN_ROOT

CONFIG_DIR = PLUGIN_ROOT / "configs"
CONFIG_NAME = "base"
OVERRIDES_ENV = "MOIRAI_CONFIG_OVERRIDES"
FAMILIES = ("lmstudio", "deepseek", "kcl", "openai")

_installed: DictConfig | None = None


def host_gateway() -> str:
    """WSL2 里 Windows 主机的地址：FREETOKEN_HOST 优先，其次默认路由的网关，最后 localhost。"""
    env = os.environ.get("FREETOKEN_HOST")
    if env:
        return env
    try:
        with open("/proc/net/route") as handle:
            for line in handle.readlines()[1:]:
                parts = line.split()
                if len(parts) > 2 and parts[1] == "00000000":
                    return ".".join(str(b) for b in struct.pack("<L", int(parts[2], 16)))
    except OSError:
        pass
    return "localhost"


def register_resolvers() -> None:
    if not OmegaConf.has_resolver("moirai_project_root"):
        OmegaConf.register_new_resolver("moirai_project_root", lambda: str(PLUGIN_ROOT), use_cache=True)
    if not OmegaConf.has_resolver("host_gateway"):
        OmegaConf.register_new_resolver("host_gateway", host_gateway, use_cache=True)


register_resolvers()


def compose(overrides: Sequence[str] = ()) -> DictConfig:
    """组合 configs/base.yaml；环境变量 MOIRAI_CONFIG_OVERRIDES 里的覆盖项排在参数之前。"""
    from hydra import compose as hydra_compose
    from hydra import initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra

    items = [*shlex.split(os.environ.get(OVERRIDES_ENV, "")), *overrides]
    if GlobalHydra.instance().is_initialized():
        return hydra_compose(config_name=CONFIG_NAME, overrides=items)
    with initialize_config_dir(config_dir=str(CONFIG_DIR), version_base=None):
        return hydra_compose(config_name=CONFIG_NAME, overrides=items)


def add_override(item: str) -> None:
    """给本进程之后的每次组合追加一个覆盖项，例如 retrieval.encoder.api_url='http://…'。"""
    os.environ[OVERRIDES_ENV] = " ".join(filter(None, (os.environ.get(OVERRIDES_ENV, ""), shlex.quote(item))))


def install(cfg: DictConfig) -> None:
    """src/main.py 把 Hydra 已组合好的配置交给本进程里的工具，工具不再自己组合。"""
    global _installed
    _installed = cfg


def current() -> DictConfig:
    return _installed if _installed is not None else compose()


def _secret(env_name: str | None) -> str:
    return os.environ.get(env_name, "") if env_name else ""


def _plain(value: Any) -> Any:
    if isinstance(value, DictConfig) or OmegaConf.is_list(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def model_file(name: str) -> DictConfig:
    return OmegaConf.load(CONFIG_DIR / "models" / f"{name}.yaml")


def legacy_settings(cfg: DictConfig | None = None) -> SimpleNamespace:
    """开发脚本过去从 run_config.py 读的大写名字，现在都由 configs/ 组合得出；密钥只取自环境变量。"""
    cfg = cfg if cfg is not None else current()
    selected = cfg.models
    out: dict[str, Any] = {
        "MODEL_TYPE": selected.type,
        "TIMEOUT": float(selected.backend.timeout_seconds),
        "LLM_CONCURRENCY": int(cfg.run.llm_concurrency),
    }
    for family in FAMILIES:
        model = selected if selected.type == family else model_file(cfg.providers[family])
        prefix = family.upper()
        out[f"{prefix}_API_URL"] = model.backend.base_url
        out[f"{prefix}_API_KEY"] = _secret(model.backend.get("api_key_env"))
        out[f"{prefix}_MODEL"] = model.model.model_id

    realtime = cfg.realtime
    typesafe = realtime.typesafe
    out.update({
        "EVENT_MODE": realtime.event_mode,
        "MOOD_SOURCE": realtime.mood_source,
        "RECALL_BENCHMARK_ENABLED": realtime.recall_benchmark,
        "TYPESAFE_ENABLED": typesafe.enabled,
        "TYPESAFE_API_KEY": _secret(typesafe.api_key_env),
        "TYPESAFE_BASE_URL": typesafe.base_url,
        "TYPESAFE_MODEL": typesafe.model,
        "TYPESAFE_TIMEOUT": typesafe.timeout_seconds,
        "TYPESAFE_TOPIC_ENABLED": typesafe.topic_enabled,
        "TYPESAFE_EVENT_ENABLED": typesafe.event_enabled,
        "TYPESAFE_TOPIC_BACKFILL": typesafe.topic_backfill,
        "TYPESAFE_EVENT_BACKFILL": typesafe.event_backfill,
        "TYPESAFE_MIN_CONFIDENCE": typesafe.min_confidence,
        "TYPESAFE_CUSTOM_TAG_MIN_SCORE": typesafe.custom_tag_min_score,
    })

    encoder, rerank = cfg.retrieval.encoder, cfg.retrieval.rerank
    out.update({
        "RETRIEVAL_ENCODER_ENABLED": encoder.enabled,
        "RETRIEVAL_ENCODER_PROVIDER": encoder.provider,
        "RETRIEVAL_ENCODER_MODEL": encoder.model,
        "RETRIEVAL_ENCODER_API_URL": encoder.api_url,
        "RETRIEVAL_ENCODER_API_KEY": _secret(encoder.api_key_env),
        "RETRIEVAL_ENCODER_DIMENSIONS": encoder.dimensions,
        "RETRIEVAL_ENCODER_BATCH_INTERVAL_MS": encoder.batch_interval_ms,
        "RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS": encoder.request_interval_ms,
        "RETRIEVAL_ENCODER_REQUEST_BATCH_SIZE": encoder.request_batch_size,
        "RETRIEVAL_ENCODER_CONCURRENCY": encoder.concurrency,
        "RETRIEVAL_ENCODER_TIMEOUT": encoder.timeout_seconds,
        "RETRIEVAL_ENCODER_RETRY_MAX": encoder.retry_max,
        "RETRIEVAL_ENCODER_RETRY_DELAY_MS": encoder.retry_delay_ms,
        "RETRIEVAL_RERANK_ENABLED": rerank.enabled,
        "RETRIEVAL_RERANK_MODEL": rerank.model,
        "RETRIEVAL_RERANK_API_URL": rerank.api_url,
        "RETRIEVAL_RERANK_API_KEY": _secret(rerank.api_key_env),
        "RETRIEVAL_RERANK_MAX_CANDIDATES": rerank.max_candidates,
        "RETRIEVAL_RERANK_TIMEOUT": rerank.timeout_seconds,
        "RETRIEVAL_RERANK_RETRY_MAX": rerank.retry_max,
    })

    tools, data = cfg.canon_tools, cfg.data
    out.update({
        "CANON_MODEL_TYPE": tools.model_type,
        "CANON_JUDGE_MODEL_TYPE": tools.judge_model_type,
        "CANON_CHAT_MODEL_TYPE": tools.chat_model_type,
        "CANON_CONCURRENCY": tools.concurrency,
        "CANON_TIMEOUT": tools.timeout_seconds,
        "CANON_BASELINE": tools.baseline,
        "CANON_PRICE_IN": tools.price_in,
        "CANON_PRICE_OUT": tools.price_out,
        "CANON_PACK": data.story_pack,
        "CANON_PROBES": data.probes,
        "CANON_SCENES": str(data.samples),
        "CANON_CHARACTER": data.default_character,
    })
    return SimpleNamespace(**{name: _plain(value) for name, value in out.items()})
