import asyncio

from app.ai.providers import MockProvider, get_provider, grounded_mock_reply, tokenize_overlap
from app.config import Settings


def run(coro):
    return asyncio.run(coro)


def test_mock_provider_is_clearly_labelled() -> None:
    result = run(MockProvider().generate("Explain quadratic equations"))
    assert result.mock is True
    assert result.provider == "mock"
    assert "mock AI response" in result.text
    assert result.tokens_in >= 1 and result.tokens_out >= 1
    assert result.estimated_cost > 0


def test_mock_provider_never_needs_credentials() -> None:
    assert run(MockProvider().generate("hello")).text


def test_default_settings_select_the_mock_provider() -> None:
    assert get_provider(Settings()).name == "mock"


def test_real_provider_without_key_falls_back_to_mock() -> None:
    for name in ("openai", "azure_openai", "gemini"):
        provider = get_provider(Settings(ai_provider=name))
        assert provider.name == "mock", name


def test_retrieval_overlap_scores_relevant_text_higher() -> None:
    query = "explain quadratic equations roots"
    relevant = "Quadratic equations have roots found by factoring"
    unrelated = "The French revolution began in 1789"
    assert tokenize_overlap(query, relevant) > tokenize_overlap(query, unrelated)


def test_overlap_handles_empty_input() -> None:
    assert tokenize_overlap("", "text") == 0.0
    assert tokenize_overlap("query words", "") == 0.0


def test_mock_reply_does_not_echo_the_system_prompt() -> None:
    prompt = (
        "Feature=study_buddy prompt_version=1\nAuthorized materials:\n"
        "AWS Cloud is a rented computing service described in the course notes.\n\n"
        "Learner question: can you tell me what is AWS cloud"
    )
    text = grounded_mock_reply(prompt)
    assert "mock AI response" in text
    assert "Feature=study_buddy" not in text
    assert "prompt_version" not in text
    assert "rented computing service" in text


def test_mock_reply_without_materials_does_not_invent_a_source() -> None:
    prompt = (
        "Feature=study_buddy prompt_version=1\nAuthorized materials:\nNo retrieved materials.\n\n"
        "Learner question: can you tell me what is AWS cloud"
    )
    text = grounded_mock_reply(prompt)
    assert "No approved course material matched" in text
    assert "AWS Cloud is a synthetic" not in text
    assert "Feature=" not in text
