# services/pressure_worker/app/consumer.py
import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aio_pika
from database import get_db_session
from models import VehicleState
from sqlalchemy.dialects.postgresql import insert as pg_insert
from worker_config import settings

logger = logging.getLogger(__name__)


class TelemetryConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.queue = None
        self.buffer: list[dict[str, Any]] = []
        self.messages_to_ack: list[aio_pika.IncomingMessage] = []
        self._lock = asyncio.Lock()
        self.running = False

    async def connect(self):
        """Conexión robusta a RabbitMQ y suscripción a la cola."""
        self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=settings.batch_size * 2)

        exchange = await self.channel.declare_exchange(
            settings.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        self.queue = await self.channel.declare_queue(settings.queue_name, durable=True)
        await self.queue.bind(exchange, routing_key=settings.routing_key)
        logger.info("Consumidor conectado a RabbitMQ y cola suscrita: %s", settings.queue_name)

    async def flush_buffer(self):
        """Vuelca los mensajes acumulados en vehicle_state por lotes."""
        async with self._lock:
            if not self.buffer:
                return

            records = self.buffer
            messages = self.messages_to_ack
            self.buffer = []
            self.messages_to_ack = []

        try:
            # Descartar duplicados dentro del lote quedándose con el más reciente por vehículo
            latest_by_vehicle = {}
            for rec in records:
                latest_by_vehicle[rec["vehicle_id"]] = rec

            values_to_upsert = []
            for rec in latest_by_vehicle.values():
                dt = datetime.fromisoformat(rec["last_seen_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                values_to_upsert.append(
                    {
                        "vehicle_id": rec["vehicle_id"],
                        "zone_id": rec.get("zone_id"),
                        "latitude": rec.get("lat"),
                        "longitude": rec.get("lon"),
                        "status": rec.get("status", "available"),
                        "last_seen_at": dt,
                    }
                )

            with get_db_session() as session:
                for chunk in [
                    values_to_upsert[i : i + 500]
                    for i in range(0, len(values_to_upsert), 500)
                ]:
                    stmt = pg_insert(VehicleState).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[VehicleState.vehicle_id],
                        set_={
                            "zone_id": stmt.excluded.zone_id,
                            "latitude": stmt.excluded.latitude,
                            "longitude": stmt.excluded.longitude,
                            "status": stmt.excluded.status,
                            "last_seen_at": stmt.excluded.last_seen_at,
                        },
                    )
                    session.execute(stmt)

            for msg in messages:
                await msg.ack()

            logger.info("Volcados %d eventos de telemetría a vehicle_state.", len(records))
        except Exception:
            logger.exception("Error guardando lote de telemetría en base de datos.")
            # Nack para reintento en caso de error transitorio
            for msg in messages:
                await msg.nack(requeue=True)

    async def start_consuming(self):
        """Inicia el bucle de consumo de eventos de telemetría."""
        self.running = True

        async def on_message(message: aio_pika.IncomingMessage):
            try:
                payload = json.loads(message.body.decode())
                async with self._lock:
                    self.buffer.append(payload)
                    self.messages_to_ack.append(message)

                if len(self.buffer) >= settings.batch_size:
                    await self.flush_buffer()
            except Exception:
                logger.exception("Mensaje de telemetría corrupto o con formato no JSON.")
                await message.reject(requeue=False)

        await self.queue.consume(on_message)
        logger.info("Escuchando mensajes en cola %s...", settings.queue_name)

        while self.running:
            await asyncio.sleep(settings.flush_interval_seconds)
            await self.flush_buffer()

    async def close(self):
        self.running = False
        await self.flush_buffer()
        if self.connection:
            await self.connection.close()
