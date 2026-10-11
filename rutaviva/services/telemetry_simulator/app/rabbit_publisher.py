# rabbit_publisher.py
import asyncio
import json
import logging
import aio_pika
from aio_pika import Message, DeliveryMode
from config import (
    RABBITMQ_URL, EXCHANGE_NAME, QUEUE_NAME, ROUTING_KEY,
    PUBLISHER_CONFIRMS, MAX_CONCURRENCIA,
)

logger = logging.getLogger(__name__)

class RabbitPublisher:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENCIA)

    async def connect(self):
        """Establece conexión robusta y declara la topología."""
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        # Un solo canal para publicación; el paralelismo real viene del semáforo
        self.channel = await self.connection.channel(
            publisher_confirms=PUBLISHER_CONFIRMS
        )
        # Declarar exchange de tipo topic (permite filtrar por routing key)
        self.exchange = await self.channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        # Declarar cola y enlazarla
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(self.exchange, routing_key=ROUTING_KEY)
        logger.info("Conectado a RabbitMQ y topología declarada.")

    async def publish_batch(self, payloads: list[dict]):
        """Publica un lote de mensajes controlando la concurrencia."""
        async with self.semaphore:
            for payload in payloads:
                message = Message(
                    body=json.dumps(payload).encode(),
                    delivery_mode=DeliveryMode.NOT_PERSISTENT,  # no persistente = más rápido
                    content_type="application/json",
                )
                await self.exchange.publish(
                    message,
                    routing_key=ROUTING_KEY,
                )

    async def close(self):
        if self.connection:
            await self.connection.close()