"""
ai_interface.py — selectable OpenAI-compatible client shim
Release: v1.31.3 (fix: .query supports positional args)
Requires: openai>=1.0.0
"""

from __future__ import annotations

import os
import time
from modules.provider_registry import ProviderRegistry, validate
from typing import Generator, Iterable, List, Optional

from openai import OpenAI
from openai._exceptions import APIError, RateLimitError, APITimeoutError, APIConnectionError


DEFAULT_BASE_URL = os.getenv("BASETEN_BASE_URL", "https://inference.baseten.co/v1")
DEFAULT_MODEL    = os.getenv("BASETEN_MODEL", "openai/gpt-oss-120b")
DEFAULT_TIMEOUT  = float(os.getenv("OPENAI_API_TIMEOUT", "60"))


def _mk_client(api_key: Optional[str] = None,
               base_url: Optional[str] = None,
               timeout: Optional[float] = None) -> OpenAI:
    return OpenAI(api_key=api_key or "local-no-key", base_url=base_url,
                  timeout=timeout or DEFAULT_TIMEOUT, max_retries=0)


def _safe_error(error):
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return "Authentication failed. Check the selected provider's API key and access permissions."
    if isinstance(error, APITimeoutError):
        return "Inference timed out. Check the selected endpoint and model server."
    if isinstance(error, APIConnectionError):
        return "Cannot connect to the selected inference endpoint. Check its base URL and server availability."
    return f"Inference request failed (HTTP {status or 'unknown'}). Check the selected model, endpoint, and provider limits."


def _retryable(func, /, *, retries: int = 2, backoff: float = 0.8):
    def _wrapped(*args, **kwargs):
        delay = backoff
        last_err = None
        for attempt in range(retries + 1):
            try:
                return func(*args, **kwargs)
            except (RateLimitError, APITimeoutError, APIConnectionError, APIError) as e:
                last_err = e
                if getattr(e, "status_code", None) in (400, 401, 403, 404) or attempt >= retries:
                    break
                time.sleep(delay)
                delay *= 2
        raise RuntimeError(_safe_error(last_err)) from None
    return _wrapped


class AIInterface:
    """Back-compat wrapper exposing multiple method names used in older code."""

    def __init__(self,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: Optional[float] = None,
                 provider: Optional[str] = None,
                 registry=None):
        self.registry = registry or ProviderRegistry()
        self.provider = provider or self.registry.read_selected()
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.client = None
        self._configuration_error = self.registry.error
        if self.provider is None:
            self.base_url = self.model = ""
            self._has_api_key = False
            return
        config = self.registry.get(self.provider)
        for key, value in (("api_key", api_key), ("base_url", base_url), ("model", model)):
            if value is not None:
                config[key] = value
        self.base_url, self.model = config["base_url"], config["model"]
        self._has_api_key = bool(config["api_key"])
        try:
            validate(config)
            if self.provider != "local" and not self._has_api_key:
                raise ValueError("API key missing for the selected provider. Configure it in Tools → Inference Provider.")
            self.client = _mk_client(config["api_key"], self.base_url, self.timeout)
        except ValueError as error:
            self._configuration_error = str(error)

    def _require_client(self):
        if self.client is None:
            raise RuntimeError(self._configuration_error or "Configure an inference provider first.")
        return self.client

    def get_config(self) -> dict:
        """Return a small runtime snapshot for launcher/debug scripts."""
        return {
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "provider": self.provider,
            "has_api_key": self._has_api_key,
        }

    # ---------- Core methods ----------

    @_retryable
    def chat(self,
             *,
             messages: List[dict],
             model: Optional[str] = None,
             temperature: float = 1.0,
             top_p: float = 1.0,
             max_tokens: int = 1000,
             presence_penalty: float = 0.0,
             frequency_penalty: float = 0.0,
             stop: Optional[Iterable[str]] = None,
             extra: Optional[dict] = None) -> str:
        kwargs = dict(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
        )
        if stop:
            kwargs["stop"] = list(stop)
        if extra:
            kwargs.update(extra)
        resp = self._require_client().chat.completions.create(**kwargs)
        if not resp.choices:
            return ""
        return resp.choices[0].message.content or ""

    def stream(self,
               *,
               messages: List[dict],
               model: Optional[str] = None,
               temperature: float = 1.0,
               top_p: float = 1.0,
               max_tokens: int = 1000,
               presence_penalty: float = 0.0,
               frequency_penalty: float = 0.0,
               stop: Optional[Iterable[str]] = None,
               include_usage: bool = True,
               continuous_usage_stats: bool = True,
               extra: Optional[dict] = None) -> Generator[str, None, None]:
        kwargs = dict(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=True,
            stream_options={
                "include_usage": include_usage,
                "continuous_usage_stats": continuous_usage_stats,
            },
        )
        if stop:
            kwargs["stop"] = list(stop)
        if extra:
            kwargs.update(extra)

        if self.provider != "baseten":
            kwargs.pop("stream_options", None)
        opener = _retryable(self._require_client().chat.completions.create)
        response = opener(**kwargs)
        try:
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except APIError as error:
            raise RuntimeError(_safe_error(error)) from None

    # ---------- Convenience ----------

    def quick_ask(self,
                  prompt: str,
                  *,
                  system: Optional[str] = None,
                  model: Optional[str] = None,
                  stream: bool = False,
                  **kw):
        messages: List[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        if stream:
            return self.stream(messages=messages, model=model, **kw)
        return self.chat(messages=messages, model=model, **kw)

    # ---------- Back-compat aliases ----------

    def generate(self, *args, **kwargs):
        return self.chat(*args, **kwargs)

    def complete(self, *args, **kwargs):
        return self.chat(*args, **kwargs)

    def chat_stream(self, *args, **kwargs):
        return self.stream(*args, **kwargs)

    # ---------- Back-compat entry points ----------

    def query(self, *args, **kwargs):
        """Accepts positional or keyword usage.
        Forms supported:
          ai.query(messages=[...], stream=False, **kw)
          ai.query("prompt")
          ai.query("prompt", "system/prefix")
        """
        messages = kwargs.pop("messages", None)
        prompt = kwargs.pop("prompt", None)
        system = kwargs.pop("system", None)
        stream = kwargs.pop("stream", False)

        # normalize positional args
        if args:
            if len(args) == 1:
                prompt = args[0]
            else:
                prompt = args[0]
                system = args[1]

        if messages is None:
            if prompt is None:
                raise ValueError("query() requires messages=[...] or a prompt string")
            msgs: List[dict] = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": str(prompt)})
        else:
            msgs = messages

        if stream:
            return self.stream(messages=msgs, **kwargs)
        return self.chat(messages=msgs, **kwargs)

    def stream_query(self, *args, **kwargs) -> Generator[str, None, None]:
        kwargs["stream"] = True
        gen = self.query(*args, **kwargs)
        # ensure a generator is returned
        if hasattr(gen, "__iter__") and not isinstance(gen, (str, bytes)):
            return gen
        # fallback: wrap string into a one-shot generator
        def _one():
            yield str(gen)
        return _one()


def make_default() -> AIInterface:
    return AIInterface()
