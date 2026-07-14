"""Strategy catalog endpoint: every discovered plugin with its parameter space."""

from fastapi import APIRouter
from pydantic import BaseModel

from quantlab.interfaces.api.deps import ContainerDep
from quantlab.strategies.base import ParameterSpec, ParamValue, StrategyMetadata

router = APIRouter(prefix="/strategies", tags=["strategies"])


class ParameterOut(BaseModel):
    name: str
    kind: str
    default: ParamValue
    low: float | None
    high: float | None
    step: float | None
    choices: tuple[str, ...] | None

    @classmethod
    def from_spec(cls, spec: ParameterSpec) -> "ParameterOut":
        return cls(
            name=spec.name,
            kind=spec.kind,
            default=spec.default,
            low=spec.low,
            high=spec.high,
            step=spec.step,
            choices=spec.choices,
        )


class StrategyOut(BaseModel):
    strategy_id: str
    name: str
    category: str
    description: str
    parameters: list[ParameterOut]

    @classmethod
    def from_metadata(cls, metadata: StrategyMetadata) -> "StrategyOut":
        return cls(
            strategy_id=metadata.strategy_id,
            name=metadata.name,
            category=metadata.category,
            description=metadata.description,
            parameters=[ParameterOut.from_spec(spec) for spec in metadata.parameters],
        )


@router.get("", response_model=list[StrategyOut])
def list_strategies(container: ContainerDep) -> list[StrategyOut]:
    """Return every auto-discovered strategy plugin."""
    return [
        StrategyOut.from_metadata(metadata)
        for metadata in container.strategy_registry.list_metadata()
    ]
