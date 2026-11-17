"""模型适配层 —— 对应 pi 的 `pi-ai`。

对上暴露统一的 Provider 接口，对下翻译各家厂商的 API 差异。
"""
from .base import ModelConfig, Provider, ProviderError
from .openai_compat import OpenAICompatibleProvider

__all__ = [
    "ModelConfig",
    "Provider",
    "ProviderError",
    "OpenAICompatibleProvider",
]
