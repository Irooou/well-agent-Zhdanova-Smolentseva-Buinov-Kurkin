"""Подключение языковой модели через OpenAI-совместимый API."""

import os

from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[2]


def get_llm_config() -> dict:

    load_dotenv(ROOT / ".env")

    config = {
        "base_url": os.getenv("LLM_BASE_URL"),
        "api_key": os.getenv("LLM_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
    }

    for name, value in config.items():
        if not value:
            raise RuntimeError(
                f"Не задана настройка LLM: {name}"
            )

    return config


def create_client() -> OpenAI:

    config = get_llm_config()

    return OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=30.0,
        max_retries=0,
    )


def ask_llm(messages: list[dict]) -> str:

    config = get_llm_config()
    client = create_client()

    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("LLM вернула пустой ответ.")

    return content