"""Provided LLM transport for module 15 (LLMs in pipelines).

A thin, swappable client over two providers — a local Ollama server and an
OpenAI-compatible HTTP API — built on raw `httpx` (no `ollama` or `openai`
SDK dependency). Tasks 02-06 import `get_client()` and use it as a pipeline
component; task 01 is the one task that reaches past this file and builds a
resilience layer (retry/reask/fallback) on top of it in its own `src/`.

Config is read from the environment, all with local-Ollama defaults, so a
learner running everything against the module's docker-compose Ollama needs
to set nothing:

  LLM_PROVIDER     "ollama" | "openai"      default "ollama"
  LLM_MODEL        chat/generation model     default "qwen2.5:7b-instruct"
  LLM_EMBED_MODEL  embedding model           default "nomic-embed-text"
  LLM_BASE_URL     provider base URL         default "http://localhost:11439" (ollama)
                                              default "https://api.openai.com/v1" (openai)
  LLM_API_KEY      bearer token              openai only, no default
  LLM_TIMEOUT      request timeout, seconds  default 120.0

Importing this module has zero side effects: no client is constructed, no
network call is made, until `get_client()` (or a provider class) is
explicitly instantiated and used.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import httpx
import numpy as np

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11439"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "qwen2.5:7b-instruct"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TIMEOUT = 120.0


class LLMClient(ABC):
    """Provider-agnostic interface every pipeline task codes against."""

    @abstractmethod
    def generate(self, prompt, *, system=None, format=None, temperature=0.0, options=None) -> str:
        """Single-turn completion. Returns the text content.

        `format`: None for free text, "json" for provider JSON mode, or a
        JSON-schema dict for structured output (Ollama passes it through to
        its `format` field; OpenAI maps it to `response_format`).
        """
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages, *, format=None, temperature=0.0) -> str:
        """Multi-turn chat. `messages` is a list of {"role", "content"}
        dicts. Returns the text content of the assistant's reply."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batched embedding. Returns one vector per input text, same
        order. Providers without a true batch endpoint loop internally."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def embed_model(self) -> str:
        raise NotImplementedError


class OllamaClient(LLMClient):
    def __init__(self, base_url=None, model=None, embed_model=None, timeout=None):
        self._base_url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self._model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        self._embed_model = embed_model or os.environ.get("LLM_EMBED_MODEL") or DEFAULT_EMBED_MODEL
        self._timeout = timeout or float(os.environ.get("LLM_TIMEOUT") or DEFAULT_TIMEOUT)

    @property
    def model(self) -> str:
        return self._model

    @property
    def embed_model(self) -> str:
        return self._embed_model

    def generate(self, prompt, *, system=None, format=None, temperature=0.0, options=None) -> str:
        body = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, **(options or {})},
        }
        if system is not None:
            body["system"] = system
        if format is not None:
            body["format"] = format
        resp = httpx.post(f"{self._base_url}/api/generate", json=body, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()["response"]

    def chat(self, messages, *, format=None, temperature=0.0) -> str:
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format is not None:
            body["format"] = format
        resp = httpx.post(f"{self._base_url}/api/chat", json=body, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Ollama's /api/embeddings has no batch mode -- loop per text.
        out = []
        for text in texts:
            resp = httpx.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._embed_model, "prompt": text},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            out.append(resp.json()["embedding"])
        return out


class OpenAIClient(LLMClient):
    def __init__(self, base_url=None, model=None, embed_model=None, api_key=None, timeout=None):
        self._base_url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self._model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        self._embed_model = embed_model or os.environ.get("LLM_EMBED_MODEL") or DEFAULT_EMBED_MODEL
        self._api_key = api_key or os.environ.get("LLM_API_KEY")
        self._timeout = timeout or float(os.environ.get("LLM_TIMEOUT") or DEFAULT_TIMEOUT)

    @property
    def model(self) -> str:
        return self._model

    @property
    def embed_model(self) -> str:
        return self._embed_model

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _response_format(format):
        if format is None:
            return None
        if format == "json":
            return {"type": "json_object"}
        # JSON-schema dict -> OpenAI structured output shape.
        return {"type": "json_schema", "json_schema": {"name": "response", "schema": format, "strict": True}}

    def generate(self, prompt, *, system=None, format=None, temperature=0.0, options=None) -> str:
        messages = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, format=format, temperature=temperature)

    def chat(self, messages, *, format=None, temperature=0.0) -> str:
        body = {"model": self._model, "messages": messages, "temperature": temperature}
        response_format = self._response_format(format)
        if response_format is not None:
            body["response_format"] = response_format
        resp = httpx.post(
            f"{self._base_url}/chat/completions", json=body, headers=self._headers(), timeout=self._timeout
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self._base_url}/embeddings",
            json={"model": self._embed_model, "input": texts},
            headers=self._headers(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [row["embedding"] for row in sorted(data, key=lambda r: r["index"])]


def get_client() -> LLMClient:
    """Factory: build the client selected by LLM_PROVIDER (default "ollama").
    This is the one place task code should call to obtain a client — never
    instantiate OllamaClient/OpenAIClient directly, so swapping providers is
    a single env var change."""
    provider = (os.environ.get("LLM_PROVIDER") or "ollama").lower()
    if provider == "ollama":
        return OllamaClient()
    if provider == "openai":
        return OpenAIClient()
    raise ValueError(f"unknown LLM_PROVIDER: {provider!r} (expected 'ollama' or 'openai')")


def cosine(a, b) -> float:
    """Cosine similarity between two vectors (list or ndarray)."""
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


__all__ = ["LLMClient", "OllamaClient", "OpenAIClient", "get_client", "cosine"]
