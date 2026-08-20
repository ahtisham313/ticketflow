"""In-process WebSocket channel membership and event broadcasting."""

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

DASHBOARD_CHANNEL = "dashboard"


def ticket_channel(ticket_id: object) -> str:
    """Return the canonical channel name for one ticket."""

    return f"ticket:{ticket_id}"


class ConnectionManager:
    """Track this API process's WebSockets by logical subscription channel."""

    def __init__(self) -> None:
        self._connections: defaultdict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        """Accept and register an already authenticated, authorized socket."""

        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        """Remove a socket and discard an empty channel."""

        async with self._lock:
            connections = self._connections.get(channel)
            if connections is None:
                return

            connections.discard(websocket)
            if not connections:
                del self._connections[channel]

    async def broadcast(self, channel: str, event: dict[str, Any]) -> None:
        """Send JSON to a channel and clean connections whose send failed."""

        async with self._lock:
            connections = tuple(self._connections.get(channel, ()))

        if not connections:
            return

        # Do not hold the membership lock while waiting on client network I/O.
        results = await asyncio.gather(
            *(websocket.send_json(event) for websocket in connections),
            return_exceptions=True,
        )

        stale_connections: list[WebSocket] = []
        for websocket, result in zip(connections, results, strict=True):
            if not isinstance(result, BaseException):
                continue

            stale_connections.append(websocket)
            if not isinstance(result, (OSError, WebSocketDisconnect)):
                logger.error(
                    "Unexpected WebSocket broadcast failure on channel %s",
                    channel,
                    exc_info=(type(result), result, result.__traceback__),
                )

        if not stale_connections:
            return

        async with self._lock:
            current_connections = self._connections.get(channel)
            if current_connections is None:
                return

            current_connections.difference_update(stale_connections)
            if not current_connections:
                del self._connections[channel]


connection_manager = ConnectionManager()
