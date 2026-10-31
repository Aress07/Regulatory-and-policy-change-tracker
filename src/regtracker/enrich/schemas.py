"""Output contract for change enrichment. The LLM explains a change; it never decides one."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Topic = Literal[
    "data_protection",
    "ai_governance",
    "cybersecurity",
    "platform_liability",
    "competition",
    "data_sharing",
    "transparency",
    "enforcement_penalties",
    "scope_definitions",
    "other",
]
Sector = Literal[
    "all",
    "healthcare",
    "finance",
    "public_sector",
    "online_platforms",
    "manufacturing",
    "telecom",
    "education",
    "other",
]
Impact = Literal["low", "medium", "high"]

TOPICS: list[str] = list(Topic.__args__)  # type: ignore[attr-defined]
SECTORS: list[str] = list(Sector.__args__)  # type: ignore[attr-defined]
IMPACTS: list[str] = list(Impact.__args__)  # type: ignore[attr-defined]


class ChangeAnalysis(BaseModel):
    summary: str = Field(max_length=500, description="Plain-language, 1-3 sentences")
    topics: list[Topic] = Field(min_length=1, max_length=3)
    sectors: list[Sector] = Field(min_length=1, max_length=3)
    impact: Impact
    impact_rationale: str = Field(max_length=300)


def strict_json_schema() -> dict[str, Any]:
    """Schema for Groq strict Structured Outputs: every property required, no extra properties.

    Length limits are left to Pydantic validation, since constrained decoding may not support
    every JSON Schema keyword.
    """
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string", "enum": TOPICS}},
            "sectors": {"type": "array", "items": {"type": "string", "enum": SECTORS}},
            "impact": {"type": "string", "enum": IMPACTS},
            "impact_rationale": {"type": "string"},
        },
        "required": ["summary", "topics", "sectors", "impact", "impact_rationale"],
        "additionalProperties": False,
    }
