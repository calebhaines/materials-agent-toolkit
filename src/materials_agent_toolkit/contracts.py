"""Shared contracts for tools and their execution results."""

from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


@dataclass(frozen=True)
class CalculationResult:
    result: BaseModel
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    execute: Callable[[BaseModel], CalculationResult]
    assumptions: tuple[str, ...]
    references: tuple[str, ...]
    version: str = "1"
    dependencies: tuple[str, ...] = ()

    def describe(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "assumptions": list(self.assumptions),
            "references": list(self.references),
            "dependencies": list(self.dependencies),
            "side_effects": [],
            "network_access": False,
            "cost": "small, in-process calculation",
        }
