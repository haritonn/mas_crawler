import os
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage, SystemMessage

from ._native import preview_extraction, ExtractionPreview, ExtractError

load_dotenv()


class SelectorConfig(BaseModel):
    title_selector: str = Field(description="CSS selector for the article title")
    content_selector: str = Field(
        description="CSS selector for the main content container, excluding navigation and menus"
    )


def validate_extraction(preview: ExtractionPreview) -> bool:
    """Validating ExtractionPreview object on heuristics which determine results of scrapping page."""
    return (
        preview.title_matches > 0
        and bool(preview.title.strip())
        and preview.content_matches > 0
        and preview.text_length > 0
    )


def configure_extraction(html: str, url: str, max_attempts: int = 3) -> SelectorConfig:
    """Propose and check CSS selectors within a bounded number of attempts."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    feedback = None
    for _ in range(max_attempts):
        selectors = propose_selectors(html, feedback)
        try:
            preview = preview_extraction(
                html,
                url,
                title_selector=selectors.title_selector,
                content_selector=selectors.content_selector,
            )
        except ExtractError as error:
            problem = f"Invalid extraction selectors: {error}"
        else:
            if validate_extraction(preview):
                return selectors
            problem = (
                f"title_matches={preview.title_matches}, "
                f"title={preview.title!r}, "
                f"content_matches={preview.content_matches}, "
                f"text_length={preview.text_length}. "
                "Both selectors must match, and title and content must be nonempty."
            )

        feedback = f"Previous selectors: {selectors.model_dump_json()}. {problem}"

    raise RuntimeError(
        f"Failed to configure extraction after {max_attempts} attempts. {feedback}"
    )


def propose_selectors(html: str, feedback: str | None = None) -> SelectorConfig:
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
    if feedback:
        feedback_msg = HumanMessage(f"""
            Your previous call was incorrect. Consider this feedback and retry with another CSS-selectors:\n {feedback}
            """)
        model_list = [system_msg, human_msg, feedback_msg]
    else:
        model_list = [system_msg, human_msg]

    result = structured_model.invoke(model_list)
    return SelectorConfig.model_validate(result)
