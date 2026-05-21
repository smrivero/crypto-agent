import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def _set_test_env():
    """Inject placeholder secrets so Settings validation passes without a .env file."""
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("MODEL_NAME", "gpt-4o-mini")
