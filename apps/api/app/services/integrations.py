from __future__ import annotations

from typing import Any

from aiokafka import AIOKafkaProducer

from apps.api.app.config import Settings


class EventPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            producer = AIOKafkaProducer(bootstrap_servers=self.settings.redpanda_brokers.split(","))
            await producer.start()
            await producer.send_and_wait(topic, str(payload).encode("utf-8"))
            await producer.stop()
        except Exception:
            # Local development should not fail if Redpanda is offline.
            return

