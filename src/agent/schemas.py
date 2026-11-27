"""Внутренние схемы структурированных запросов."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class Quantity(StrictModel):

    value: int | float | None = None
    unit: str | None = None


class ExperimentParameters(StrictModel):

    temperature: Quantity | None = None
    pressure_steps: list[Quantity] | None = None


class Experiment(StrictModel):

    type: str | None = None
    stream: str | None = None
    parameters: ExperimentParameters | None = None


class ParsedRequest(StrictModel):

    task_type: str | None = None
    model_id: str | None = None
    experiment: Experiment | None = None