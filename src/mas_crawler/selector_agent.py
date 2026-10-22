import os
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage, SystemMessage

load_dotenv()


class SelectorConfig(BaseModel):
    title_selector: str = Field(description="CSS selector for the article title")
    content_selector: str = Field(
        description="CSS selector for the main content container, excluding navigation and menus"
    )


def propose_selectors(html: str) -> SelectorConfig:
    """Propose title and main-content CSS selectors for an HTML page."""
    model = ChatOpenAI(
        model="deepseek/deepseek-v4.1-flash",
        api_key=lambda: os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
    )
    system_msg = SystemMessage("""
    Your task is to determine which CSS selectors can be useful for scrapping page.
    Given a HTML page, your goal is to select CSS selectors to parse title and main content of page.
    """)
    human_msg = HumanMessage(html)
    structured_model = model.with_structured_output(
        SelectorConfig, method="function_calling"
    )
    result = structured_model.invoke([system_msg, human_msg])
    return SelectorConfig.model_validate(result)
