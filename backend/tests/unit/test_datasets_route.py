"""Tests for the datasets API routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from quantlab.application.ports import DatasetRepository
from quantlab.config import Settings
from quantlab.domain.broker import BrokerCredentials
from quantlab.domain.datasets import Dataset, DatasetStatus
from quantlab.domain.market import Symbol, Timeframe
from quantlab.interfaces.api.app import create_app


class FakeRepo(DatasetRepository):
    def __init__(self, datasets: list[Dataset]) -> None:
        self._datasets = datasets

    async def get(self, symbol: Symbol, timeframe: Timeframe) -> Dataset | None:
        return None

    async def list_all(self) -> list[Dataset]:
        return self._datasets

    async def upsert(self, dataset: Dataset) -> Dataset:
        return dataset


class FakeIngestion:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Symbol], list[Timeframe]]] = []

    async def sync_all(
        self, symbols: list[Symbol] | None = None, timeframes: list[Timeframe] | None = None
    ) -> list[Dataset]:
        self.calls.append((symbols or [], timeframes or []))
        return []


class DatasetsStubContainer:
    def __init__(
        self,
        settings: Settings,
        datasets: list[Dataset] | None = None,
        credentials: BrokerCredentials | None = None,
    ) -> None:
        self.settings = settings
        self.ingestion = FakeIngestion()
        self._credentials = credentials or BrokerCredentials()
        self._datasets = datasets or []

    async def oanda_credentials(self) -> BrokerCredentials:
        return self._credentials

    async def data_ingestion(self) -> FakeIngestion:
        return self.ingestion

    @asynccontextmanager
    async def dataset_repository(self) -> AsyncIterator[DatasetRepository]:
        yield FakeRepo(self._datasets)


def build_client(app: FastAPI, container: DatasetsStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


CONFIGURED = BrokerCredentials(api_token="valid-token-123")


async def test_list_datasets_returns_catalog(settings: Settings) -> None:
    dataset = Dataset(
        symbol=Symbol.EURUSD,
        timeframe=Timeframe.H1,
        status=DatasetStatus.READY,
        candle_count=1234,
        source="oanda",
    )
    app = create_app(settings)
    async with build_client(app, DatasetsStubContainer(settings, [dataset])) as client:
        response = await client.get("/api/v1/datasets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "EURUSD"
    assert body[0]["timeframe"] == "H1"
    assert body[0]["status"] == "ready"
    assert body[0]["candle_count"] == 1234


async def test_sync_requires_credentials(settings: Settings) -> None:
    app = create_app(settings)
    container = DatasetsStubContainer(settings)  # no credentials anywhere
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/datasets/sync", json={})
    assert response.status_code == 409
    assert "Broker settings" in response.json()["detail"]
    assert container.ingestion.calls == []


async def test_sync_schedules_background_download(settings: Settings) -> None:
    app = create_app(settings)
    container = DatasetsStubContainer(settings, credentials=CONFIGURED)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/datasets/sync",
            json={"symbols": ["EURUSD"], "timeframes": ["H1", "H4"]},
        )
    assert response.status_code == 202
    assert response.json()["pairs"] == 2
    # background task ran after the response was sent
    assert container.ingestion.calls == [([Symbol.EURUSD], [Timeframe.H1, Timeframe.H4])]


async def test_sync_defaults_to_all_symbols_and_timeframes(settings: Settings) -> None:
    app = create_app(settings)
    container = DatasetsStubContainer(settings, credentials=CONFIGURED)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/datasets/sync", json={})
    assert response.status_code == 202
    assert response.json()["pairs"] == len(Symbol) * len(Timeframe)
