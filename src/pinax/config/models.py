"""Configuration schema (brief §66). Declared as one contract up front so later phases
(AI, retrieval) don't need a breaking config migration — sections they own simply go unused
until those phases are implemented."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReaderConfig(BaseModel):
    width: int | Literal["auto"] = 86
    theme: str = "midnight"
    vim_keys: bool = True
    show_toc: bool = True
    show_agent: bool = True


class DocumentsConfig(BaseModel):
    ocr: Literal["auto", "always", "never"] = "auto"
    enhanced_pdf_parser: bool = False


class AIConfig(BaseModel):
    enabled: bool = False
    provider: Literal["openai", "anthropic", "ollama", "compatible"] = "ollama"
    model: str = ""


class RetrievalConfig(BaseModel):
    semantic: bool = False
    top_k: int = 6


class UIConfig(BaseModel):
    mouse: bool = True
    animations: bool = True


class Settings(BaseModel):
    reader: ReaderConfig = ReaderConfig()
    documents: DocumentsConfig = DocumentsConfig()
    ai: AIConfig = AIConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    ui: UIConfig = UIConfig()
