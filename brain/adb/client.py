"""HTTP client for brain tick, routine, and learning endpoints."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.agent.actions import ObserveBundle, TickLastResult, TickRequest, TickResponse
from app.learning.schemas import DeviceMemoryResponse, TrajectoryBatchRequest, TrajectoryBatchResponse
from app.ugc.operator import RoutineRequest, RoutineResponse


class BrainClient:
    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout = timeout

    async def tick(self, request: TickRequest) -> TickResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/agent/tick",
                headers=self.headers,
                json=request.model_dump(mode="json"),
            )
            resp.raise_for_status()
            return TickResponse.model_validate(resp.json())

    async def routine(self, request: RoutineRequest) -> RoutineResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/ugc/routine",
                headers=self.headers,
                json=request.model_dump(mode="json"),
            )
            resp.raise_for_status()
            return RoutineResponse.model_validate(resp.json())

    async def get_memory(self, device_id: str) -> DeviceMemoryResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/learning/memory/{device_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return DeviceMemoryResponse.model_validate(resp.json())

    async def sync_memory(self, device_id: str, entries: list[dict[str, Any]]) -> DeviceMemoryResponse:
        payload = {"device_id": device_id, "entries": entries}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/learning/memory",
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            return DeviceMemoryResponse.model_validate(resp.json())

    async def post_trajectory(self, batch: TrajectoryBatchRequest) -> TrajectoryBatchResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/learning/trajectory",
                headers=self.headers,
                json=batch.model_dump(mode="json"),
            )
            resp.raise_for_status()
            return TrajectoryBatchResponse.model_validate(resp.json())

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return resp.json()
