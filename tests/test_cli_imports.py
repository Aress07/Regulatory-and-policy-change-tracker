"""The CLI must work with only the core dependencies (CI's dbt job installs `pip install -e .`)."""

import subprocess
import sys


def test_cli_imports_without_optional_extras() -> None:
    blocked = [
        "numpy",
        "sentence_transformers",
        "torch",
        "streamlit",
        "fastapi",
        "openai",
        "pandas",
    ]
    code = (
        "import sys\n"
        f"for name in {blocked!r}:\n"
        "    sys.modules[name] = None  # any import of these now raises ImportError\n"
        "import regtracker.cli\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
