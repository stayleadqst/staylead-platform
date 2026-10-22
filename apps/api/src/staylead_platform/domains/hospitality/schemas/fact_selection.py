"""Bounded M1 candidate selection schema for low-overlap multilingual requests."""

from pydantic import BaseModel, Field


class FactSelection(BaseModel):
    fact_ids: list[str] = Field(default_factory=list, max_length=20)
