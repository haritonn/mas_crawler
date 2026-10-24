"""Shared model construction for both analysis agents."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .config import LLMConfig


def create_model(config: LLMConfig) -> ChatOpenAI:
    load_dotenv()
    base_url = os.environ.get("LLM_BASE_URL") or config.base_url
    if not os.environ.get("LLM_API_KEY"):
        raise ValueError("Set LLM_API_KEY in the environment or .env for analysis")
    if not base_url:
        raise ValueError("Set LLM_BASE_URL or llm.base_url for analysis")
    return ChatOpenAI(
        model=config.model,
        api_key=lambda: os.environ["LLM_API_KEY"],
        base_url=base_url,
    )
