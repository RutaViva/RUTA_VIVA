#!/usr/bin/env python3
"""
scripts/test_burst_ca10.py
Script de prueba de carga y ráfagas para validación de la Historia de Usuario HU-01 (Criterio CA-10).

Criterio de Aceptación:
"Given the load testing scenario, When configurable bursts are generated
(e.g., end of a concert), Then the API sustains the volume without crashing."

Permite ejecutar ráfagas configurables (por defecto 1.000 solicitudes concurrentes o hasta 5.000 req/min)
y valida que:
1. Ninguna solicitud devuelva error de servidor (HTTP 5xx).
2. El porcentaje de éxito (HTTP 201) sea >= 99%.
3. Mida throughput (req/s), latencia media y percentil 95.
"""
import argparse
import asyncio
import logging
import random
import sys
import time
from typing import Dict, List

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("BurstTestCA10")


async def send_single_trip_request(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    api_url: str,
    zone_id: int,
    latencies: List[float],
    status_counts: Dict[int, int],
) -> bool:
    payload = {
        "zone_id": zone_id,
        "base_fare": round(random.uniform(10.0, 35.0), 2),
    }
    async with semaphore:
        t0 = time.perf_counter()
        try:
            resp = await client.post(f"{api_url}/trip-requests", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            status_counts[resp.status_code] = status_counts.get(resp.status_code, 0) + 1
            return resp.status_code == 201
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            status_counts[599] = status_counts.get(599, 0) + 1
            logger.debug("Error en petición: %s", exc)
            return False


async def run_burst_benchmark(
    api_url: str,
    total_requests: int,
    concurrency: int,
    target_zone: int,
) -> bool:
    logger.info("=" * 65)
    logger.info("🚀 INICIANDO PRUEBA DE ESTRÉS / RÁFAGA (HU-01 / CA-10)")
    logger.info("   API URL:           %s", api_url)
    logger.info("   Total Solicitudes: %d", total_requests)
    logger.info("   Concurrencia Max:  %d conexiones", concurrency)
    logger.info("   Zona Objetivo:     %d (Midtown / Madison Sq Garden)", target_zone)
    logger.info("=" * 65)

    semaphore = asyncio.Semaphore(concurrency)
    latencies: List[float] = []
    status_counts: Dict[int, int] = {}

    limits = httpx.Limits(max_connections=concurrency + 20, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(15.0, connect=10.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        start_time = time.perf_counter()
        tasks = [
            send_single_trip_request(
                client=client,
                semaphore=semaphore,
                api_url=api_url,
                zone_id=target_zone,
                latencies=latencies,
                status_counts=status_counts,
            )
            for _ in range(total_requests)
        ]
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

    success_count = sum(1 for r in results if r)
    server_errors = sum(count for code, count in status_counts.items() if code >= 500)
    throughput = total_requests / max(0.001, total_time)

    latencies.sort()
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0.0

    logger.info("=" * 65)
    logger.info("📊 RESULTADOS DEL BENCHMARK:")
    logger.info("   Tiempo Total:      %.2f segundos", total_time)
    logger.info("   Throughput:        %.1f peticiones/segundo (%.0f req/min)", throughput, throughput * 60)
    logger.info("   Exitosas (201):    %d / %d (%.2f%%)", success_count, total_requests, (success_count / total_requests) * 100)
    logger.info("   Errores 5xx:       %d", server_errors)
    logger.info("   Desglose Códigos:  %s", status_counts)
    logger.info("   Latencia Promedio: %.2f ms", avg_latency)
    logger.info("   Latencia p50:      %.2f ms", p50)
    logger.info("   Latencia p95:      %.2f ms", p95)
    logger.info("   Latencia p99:      %.2f ms", p99)
    logger.info("=" * 65)

    if server_errors > 0:
        logger.error("❌ FALLO CA-10: Se presentaron %d errores 5xx de servidor.", server_errors)
        return False

    success_pct = (success_count / total_requests) * 100
    if success_pct < 98.0:
        logger.error("❌ FALLO CA-10: Tasa de éxito menor al 98%% (%.2f%%)", success_pct)
        return False

    logger.info("✅ ÉXITO CA-10: La API sostuvo la ráfaga masiva sin caídas ni errores de servidor.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Prueba de ráfaga y estrés para RutaViva (HU-01 / CA-10)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL base de la API (default: http://localhost:8000)")
    parser.add_argument("--requests", type=int, default=1000, help="Cantidad de solicitudes en la ráfaga (default: 1000)")
    parser.add_argument("--concurrency", type=int, default=50, help="Concurrencia máxima simultánea (default: 50)")
    parser.add_argument("--zone", type=int, default=161, help="ID de la zona objetivo de la ráfaga (default: 161)")

    args = parser.parse_args()

    success = asyncio.run(
        run_burst_benchmark(
            api_url=args.api_url,
            total_requests=args.requests,
            concurrency=args.concurrency,
            target_zone=args.zone,
        )
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
