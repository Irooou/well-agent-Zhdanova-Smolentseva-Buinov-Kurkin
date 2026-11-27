"""Точка подключения расчётного ПО."""

from src.agent.adapter import PVTPAdapter, TestPVTPAdapter


def create_adapter(test_mode: bool = False) -> PVTPAdapter:
    if test_mode:
        return TestPVTPAdapter()

    return PVTPAdapter()