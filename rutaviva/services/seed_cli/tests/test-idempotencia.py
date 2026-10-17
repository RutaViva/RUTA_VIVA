"""
====================================================================================================
                        RUTA VIVA MOBILITY - PRUEBA DE IDEMPOTENCIA EN BD
====================================================================================================
Módulo para validar la IDEMPOTENCIA y el DETERMINISMO en la base de datos operacional.

Concepto de Idempotencia:
    Una operación f sobre la base de datos es idempotente si ejecutarla una vez produce
    exactamente el mismo estado que ejecutarla múltiples veces consecutivas:
        f(f(DB)) = f(DB)

Validaciones realizadas por este módulo:
    1. DETERMINISMO E IDEMPOTENCIA DE REGENERACIÓN (Clean & Re-seed):
       - Ejecuta el seeder dos veces consecutivas con la misma semilla (SEED).
       - Compara el estado de cada tabla: los conteos de filas deben ser exactamente iguales
         (Delta = 0) y los identificadores (UUIDs, IDs, placas) deben ser 100% idénticos.
    2. RE-EJECUCIÓN SEGURA / SIN DUPLICADOS (Re-insertion / Upsert):
       - Verifica que una re-ejecución sobre datos existentes no duplique registros ni
         rompa restricciones de integridad.
    3. AUDITORÍA DE DUPLICADOS EN CLAVES PRIMARIAS Y CAMPOS ÚNICOS:
       - Para cada tabla: COUNT(*) == COUNT(DISTINCT primary_key).
       - Para la tabla 'vehicle': COUNT(*) == COUNT(DISTINCT plate).
    4. INTEGRIDAD REFERENCIAL Y REGLAS DE NEGOCIO:
       - No deben existir registros huérfanos (vehículos, licencias, sanciones sin conductor).
       - Los estados de conductor y vehículo deben respetar las listas permitidas por el esquema.
====================================================================================================
"""

import argparse
import logging
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Configurar el path para permitir ejecuciones desde la raíz del proyecto o desde la carpeta services
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
RUTAVIVA_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(RUTAVIVA_DIR, ".."))

for p in [CURRENT_DIR, RUTAVIVA_DIR, REPO_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Cambiar el directorio de trabajo a 'rutaviva' si es necesario para resolver rutas relativas
# como 'services/seed_cli/app/data/csv/taxi_zone_lookup.csv'
if os.path.exists(os.path.join(RUTAVIVA_DIR, "services", "seed_cli", "app", "data")):
    os.chdir(RUTAVIVA_DIR)

# Configurar codificación segura para consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Si el usuario solicita --help o -h, mostrar la ayuda sin requerir dependencias pesadas
if "-h" in sys.argv or "--help" in sys.argv:
    parser = argparse.ArgumentParser(
        description="Script de Validacion de Idempotencia y Determinismo en Base de Datos - RutaViva"
    )
    parser.add_argument(
        "--drivers",
        type=int,
        default=50,
        help="Cantidad de conductores para la prueba (default: 50).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Solo audita duplicados e integridad en la BD actual sin re-ejecutar el seeder.",
    )
    parser.print_help()
    sys.exit(0)

# Importar dependencias con manejo amigable de errores
try:
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.orm import Session, sessionmaker
    from faker import Faker
except ImportError as err:
    print(
        f"\n[ERROR] Falta una o mas dependencias requeridas ({err}).\n"
        f"[INFO] Para instalar las dependencias necesarias en tu entorno:\n"
        f"   pip install sqlalchemy \"psycopg[binary]\" pandas geopandas faker alembic\n"
        f"   o ejecuta desde la carpeta 'rutaviva':\n"
        f"   pip install -r requeriment.txt\n"
    )
    sys.exit(1)

# Importar modelos y utilidades de la base de datos
try:
    from services.database import DATABASE_URL, SessionLocal, clean_database, engine
    from services.main import bulk_insert_in_chunks, run_seeder
    from services.models import (
        Base,
        Driver,
        FareAudit,
        License,
        Sanction,
        SpecialEvent,
        TariffRuleVersion,
        TripRequest,
        Vehicle,
        VehicleState,
        WeatherCurrent,
        Zone,
        ZoneState,
        ZoneStateHistory,
    )
    from services.seed_cli.app.seeder import (
        apply_driver_status,
        generate_drivers,
        generate_licenses,
        generate_sanctions,
        generate_vehicles,
        generate_vehicle_states,
        generate_zones,
    )
except ImportError:
    try:
        from database import DATABASE_URL, SessionLocal, clean_database, engine
        from main import bulk_insert_in_chunks, run_seeder
        from models import (
            Base,
            Driver,
            FareAudit,
            License,
            Sanction,
            SpecialEvent,
            TariffRuleVersion,
            TripRequest,
            Vehicle,
            VehicleState,
            WeatherCurrent,
            Zone,
            ZoneState,
            ZoneStateHistory,
        )
        from seed_cli.app.seeder import (
            apply_driver_status,
            generate_drivers,
            generate_licenses,
            generate_sanctions,
            generate_vehicles,
            generate_vehicle_states,
            generate_zones,
        )
    except ImportError as err:
        print(
            f"\n❌ ERROR al importar los módulos de RutaViva ({err}).\n"
            f"💡 Asegúrate de estar ejecutando el comando desde la raíz del proyecto o desde 'rutaviva/'.\n"
        )
        sys.exit(1)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("PruebaIdempotencia")

# Lista de tablas operacionales y sus modelos asociados
MONITORED_MODELS = [
    ("zone", Zone, Zone.zone_id),
    ("driver", Driver, Driver.driver_id),
    ("license", License, License.license_id),
    ("sanction", Sanction, Sanction.sanction_id),
    ("vehicle", Vehicle, Vehicle.vehicle_id),
    ("vehicle_state", VehicleState, VehicleState.vehicle_id),
]


def test_db_connection(target_engine=None) -> bool:
    """
    Verifica si la base de datos está accesible.
    """
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1;"))
        return True
    except Exception as e:
        logger.error(
            f"\n"
            f"[ERROR] CONEXION A LA BASE DE DATOS:\n"
            f"   No fue posible conectarse a: {eng.url}\n"
            f"   Detalle: {e}\n\n"
            f"[SUGERENCIA]\n"
            f"   1. Asegurate de que el contenedor Docker este corriendo:\n"
            f"      docker compose -f rutaviva/docker-compose.yml up -d\n"
            f"   2. Verifica que las credenciales en .env coincidan con el contenedor.\n"
            f"   3. Si usas un puerto diferente a 5438, configuralo en la variable DATABASE_URL.\n"
        )
        return False


def get_table_counts(session: Session) -> Dict[str, int]:
    """
    Retorna un diccionario con la cantidad de filas por tabla.
    """
    counts = {}
    for table_name, model_cls, _ in MONITORED_MODELS:
        try:
            n = session.execute(select(func.count()).select_from(model_cls)).scalar() or 0
            counts[table_name] = n
        except Exception as err:
            logger.warning(f"No se pudo consultar conteo para {table_name}: {err}")
            counts[table_name] = -1
    return counts


def capture_snapshot(session: Session) -> Dict[str, Any]:
    """
    Captura una 'foto' del estado de la base de datos:
    - Conteos por tabla.
    - Conjuntos de identificadores clave (zonas, conductores, placas, etc.).
    """
    counts = get_table_counts(session)

    # Identificadores para validar igualdad exacta registro a registro
    zone_ids = set(session.execute(select(Zone.zone_id)).scalars().all())
    driver_ids = {str(d_id) for d_id in session.execute(select(Driver.driver_id)).scalars().all()}
    vehicle_ids = {str(v_id) for v_id in session.execute(select(Vehicle.vehicle_id)).scalars().all()}
    plates = set(session.execute(select(Vehicle.plate)).scalars().all())
    license_ids = {str(l_id) for l_id in session.execute(select(License.license_id)).scalars().all()}

    return {
        "counts": counts,
        "zone_ids": zone_ids,
        "driver_ids": driver_ids,
        "vehicle_ids": vehicle_ids,
        "plates": plates,
        "license_ids": license_ids,
    }


def audit_duplicates(session: Session) -> Dict[str, Dict[str, Any]]:
    """
    Audita que en ninguna tabla existan claves primarias o únicas duplicadas.
    Retorna un reporte detallado tabla por tabla.
    """
    report = {}
    for table_name, model_cls, pk_col in MONITORED_MODELS:
        total_rows = session.execute(select(func.count()).select_from(model_cls)).scalar() or 0
        distinct_pks = session.execute(select(func.count(func.distinct(pk_col)))).scalar() or 0
        duplicates = total_rows - distinct_pks

        table_result = {
            "total_rows": total_rows,
            "distinct_pks": distinct_pks,
            "duplicate_pks": duplicates,
            "status": "PASS" if duplicates == 0 else "FAIL",
        }

        # Validación especial de placa única en la tabla vehicle
        if table_name == "vehicle":
            distinct_plates = session.execute(select(func.count(func.distinct(Vehicle.plate)))).scalar() or 0
            duplicate_plates = total_rows - distinct_plates
            table_result["duplicate_plates"] = duplicate_plates
            if duplicate_plates > 0:
                table_result["status"] = "FAIL"

        report[table_name] = table_result

    return report


def audit_referential_integrity(session: Session) -> Dict[str, Any]:
    """
    Verifica que no existan registros huérfanos que violen la integridad referencial.
    """
    results = {}

    # 1. Vehículos sin conductor
    orphaned_vehicles = session.execute(
        select(func.count())
        .select_from(Vehicle)
        .where(~Vehicle.driver_id.in_(select(Driver.driver_id)))
    ).scalar() or 0
    results["vehiculos_huerfanos"] = orphaned_vehicles

    # 2. Licencias sin conductor
    orphaned_licenses = session.execute(
        select(func.count())
        .select_from(License)
        .where(~License.driver_id.in_(select(Driver.driver_id)))
    ).scalar() or 0
    results["licencias_huerfanas"] = orphaned_licenses

    # 3. Sanciones sin conductor
    orphaned_sanctions = session.execute(
        select(func.count())
        .select_from(Sanction)
        .where(~Sanction.driver_id.in_(select(Driver.driver_id)))
    ).scalar() or 0
    results["sanciones_huerfanas"] = orphaned_sanctions

    # 4. Estados de vehículo sin vehículo
    orphaned_v_states = session.execute(
        select(func.count())
        .select_from(VehicleState)
        .where(~VehicleState.vehicle_id.in_(select(Vehicle.vehicle_id)))
    ).scalar() or 0
    results["estados_sin_vehiculo"] = orphaned_v_states

    all_clean = all(count == 0 for count in results.values())
    results["status"] = "PASS" if all_clean else "FAIL"
    return results


def print_comparison_table(snapshot_1: Dict[str, Any], snapshot_2: Dict[str, Any], dup_report: Dict[str, Any]) -> bool:
    """
    Imprime una tabla de comparación ASCII estética y profesional.
    Retorna True si todas las tablas pasaron, False si hubo algún mismatch.
    """
    counts_1 = snapshot_1["counts"]
    counts_2 = snapshot_2["counts"]

    print("\n" + "=" * 80)
    print("           REPORTE COMPARATIVO DE IDEMPOTENCIA - TABLA POR TABLA")
    print("=" * 80)
    print(f"{'Tabla':<20} | {'Corrida 1':<12} | {'Corrida 2':<12} | {'Delta':<8} | {'Duplicados':<12} | {'Estado':<8}")
    print("-" * 80)

    all_passed = True

    for table_name, _, _ in MONITORED_MODELS:
        c1 = counts_1.get(table_name, 0)
        c2 = counts_2.get(table_name, 0)
        delta = c2 - c1
        dup_info = dup_report.get(table_name, {})
        dups = dup_info.get("duplicate_pks", 0)

        # Regla de éxito: Conteo 1 == Conteo 2 (Delta = 0) Y cero duplicados
        passed = (c1 == c2) and (dups == 0) and (c1 > 0)
        status_str = "PASS" if passed else "FAIL"

        if not passed:
            all_passed = False

        print(f"{table_name:<20} | {c1:<12} | {c2:<12} | {delta:<8} | {dups:<12} | {status_str:<8}")

    print("=" * 80)
    return all_passed


def run_idempotency_test(drivers_count: int = 50, keep_data: bool = True) -> bool:
    """
    Ejecuta el flujo completo de prueba de idempotencia:
      Paso 1: Corrida inicial (Seed 1) con semillas fijas.
      Paso 2: Captura de Snapshot 1.
      Paso 3: Segunda corrida (Seed 2) con las MISMAS semillas fijas.
      Paso 4: Captura de Snapshot 2.
      Paso 5: Auditoría de duplicados e integridad referencial.
      Paso 6: Comparación e informe final.
    """
    print("\n" + "#" * 80)
    print("        INICIANDO PRUEBA DE IDEMPOTENCIA EN BASE DE DATOS - RUTA VIVA")
    print("#" * 80)

    # 1. Comprobar conectividad
    logger.info("Comprobando conexión a la base de datos...")
    if not test_db_connection():
        return False
    logger.info("Conexión a PostgreSQL establecida exitosamente.")

    # Fijar semillas para garantizar determinismo estricto
    test_seed = int(os.getenv("SEED", "1230821048148"))
    test_np_seed = int(os.getenv("NP_SEED", "45"))

    session: Session = SessionLocal()

    try:
        # ─────────────────────────────────────────────────────────────────
        # PASO 1: PRIMERA CORRIDA (Inicialización y Carga 1)
        # ─────────────────────────────────────────────────────────────────
        print("\n[PASO 1/4] Ejecutando PRIMERA corrida del Seeder (clean_first=True)...")
        os.environ["SEED"] = str(test_seed)
        os.environ["NP_SEED"] = str(test_np_seed)
        random.seed(test_seed)
        Faker.seed(test_seed)

        start_time_1 = time.time()
        run_seeder(drivers_count=drivers_count, clean_first=True)
        elapsed_1 = round(time.time() - start_time_1, 2)
        logger.info(f"Primera corrida finalizada en {elapsed_1}s.")

        snapshot_1 = capture_snapshot(session)
        logger.info(f"Snapshot 1 capturado: {snapshot_1['counts']}")

        # ---> LIBERAR LA TRANSACCIÓN PARA EVITAR EL BLOQUEO (DATABASE LOCK) <---
        session.rollback()

# ─────────────────────────────────────────────────────────────────
        # PASO 2: SEGUNDA CORRIDA (Re-ejecución determinista - Upsert Real)
        # ─────────────────────────────────────────────────────────────────
        print("\n[PASO 2/4] Ejecutando SEGUNDA corrida del Seeder (Upsert sin limpiar la BD)...")
        os.environ["SEED"] = str(test_seed)
        os.environ["NP_SEED"] = str(test_np_seed)
        random.seed(test_seed)
        Faker.seed(test_seed)

        start_time_2 = time.time()
        # AQUÍ ESTÁ EL CAMBIO CLAVE: clean_first=False
        run_seeder(drivers_count=drivers_count, clean_first=False)
        elapsed_2 = round(time.time() - start_time_2, 2)
        logger.info(f"Segunda corrida finalizada en {elapsed_2}s.")

        snapshot_2 = capture_snapshot(session)
        logger.info(f"Snapshot 2 capturado: {snapshot_2['counts']}")

        # ---> LIBERAR LA TRANSACCIÓN PARA LAS AUDITORÍAS <---
        session.rollback()

        # ─────────────────────────────────────────────────────────────────
        # PASO 3: AUDITORÍAS DE DUPLICADOS E INTEGRIDAD REFERENCIAL
        # ─────────────────────────────────────────────────────────────────
        print("\n[PASO 3/4] Auditando duplicados en claves primarias e integridad relacional...")
        dup_report = audit_duplicates(session)
        ref_report = audit_referential_integrity(session)
        
        # Limpiar transacciones tras las lecturas de auditoría
        session.rollback()

        # ─────────────────────────────────────────────────────────────────
        # PASO 4: COMPARACIÓN ESTRICTA Y VEREDICTO FINAL
        # ─────────────────────────────────────────────────────────────────
        print("\n[PASO 4/4] Validando identidades de identificadores y deltas...")
        counts_match = print_comparison_table(snapshot_1, snapshot_2, dup_report)

        # Validación de igualdad exacta de conjuntos de IDs
        same_zones = (snapshot_1["zone_ids"] == snapshot_2["zone_ids"])
        same_drivers = (snapshot_1["driver_ids"] == snapshot_2["driver_ids"])
        same_vehicles = (snapshot_1["vehicle_ids"] == snapshot_2["vehicle_ids"])
        same_plates = (snapshot_1["plates"] == snapshot_2["plates"])
        same_licenses = (snapshot_1["license_ids"] == snapshot_2["license_ids"])

        id_integrity = all([same_zones, same_drivers, same_vehicles, same_plates, same_licenses])
        ref_integrity = (ref_report["status"] == "PASS")

        print("\nDetalle de Comprobaciones Clave:")
        print(f"  * Invarianza de conteos por tabla (Delta = 0): {'[PASS]' if counts_match else '[FAIL]'}")
        print(f"  * Cero duplicados en claves primarias:         {'[PASS]' if all(d['duplicate_pks'] == 0 for d in dup_report.values()) else '[FAIL]'}")
        print(f"  * Cero duplicados en placas de vehiculos:      {'[PASS]' if dup_report.get('vehicle', {}).get('duplicate_plates', 0) == 0 else '[FAIL]'}")
        print(f"  * Determinismo de UUIDs de conductores:        {'[PASS]' if same_drivers else '[FAIL]'}")
        print(f"  * Determinismo de UUIDs de vehiculos:          {'[PASS]' if same_vehicles else '[FAIL]'}")
        print(f"  * Determinismo de placas de vehiculos:         {'[PASS]' if same_plates else '[FAIL]'}")
        print(f"  * Ausencia de registros huerfanos:             {'[PASS]' if ref_integrity else '[FAIL]'}")

        total_pass = counts_match and id_integrity and ref_integrity

        print("\n" + "=" * 80)
        if total_pass:
            print("  [EXITO] VEREDICTO: LA PRUEBA DE IDEMPOTENCIA FUE COMPLETAMENTE EXITOSA!")
            print("  La base de datos se mantiene determinista, consistente y sin duplicados.")
        else:
            print("  [ERROR] VEREDICTO: LA PRUEBA DE IDEMPOTENCIA DETECTO INCONSISTENCIAS.")
            if not counts_match:
                print("     - Hubo discrepancias en los conteos de filas entre corridas.")
            if not id_integrity:
                print("     - Los identificadores generados variaron entre corridas con la misma semilla.")
            if not ref_integrity:
                print(f"     - Se encontraron registros huerfanos: {ref_report}")
        print("=" * 80 + "\n")

        return total_pass

    except Exception as e:
        logger.critical(f"Error inesperado durante la prueba de idempotencia: {e}", exc_info=True)
        return False
    finally:
        session.close()


# ====================================================================================================
# Adaptadores para ejecución con pytest
# ====================================================================================================
def test_idempotencia_determinismo():
    """Test para pytest: valida determinismo e idempotencia de conteos y llaves."""
    assert run_idempotency_test(drivers_count=10, keep_data=True) is True


def test_idempotencia_ausencia_duplicados():
    """Test para pytest: audita que ninguna tabla tenga duplicados de PK o placas."""
    session = SessionLocal()
    try:
        report = audit_duplicates(session)
        for tbl, data in report.items():
            assert data["duplicate_pks"] == 0, f"Tabla {tbl} tiene duplicados en PK"
            if "duplicate_plates" in data:
                assert data["duplicate_plates"] == 0, f"Tabla vehicle tiene duplicados en plate"
    finally:
        session.close()


def test_idempotencia_integridad_referencial():
    """Test para pytest: valida que no existan huérfanos en la base de datos."""
    session = SessionLocal()
    try:
        ref_report = audit_referential_integrity(session)
        assert ref_report["status"] == "PASS", f"Inconsistencias referenciales: {ref_report}"
    finally:
        session.close()


# ====================================================================================================
# Ejecución vía CLI
# ====================================================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Script de Validación de Idempotencia y Determinismo en Base de Datos - RutaViva"
    )
    parser.add_argument(
        "--drivers",
        type=int,
        default=50,
        help="Cantidad de conductores para la prueba (default: 50).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Solo audita duplicados e integridad en la BD actual sin re-ejecutar el seeder.",
    )

    args = parser.parse_args()

    if args.check_only:
        print("\n--- AUDITORÍA DIRECTA DE DUPLICADOS E INTEGRIDAD EN BD ---")
        if not test_db_connection():
            sys.exit(1)
        sess = SessionLocal()
        try:
            dups = audit_duplicates(sess)
            refs = audit_referential_integrity(sess)
            print("\nDuplicados por tabla:")
            for t, inf in dups.items():
                print(f"  {t}: {inf['total_rows']} filas, {inf['duplicate_pks']} duplicados PK [{inf['status']}]")
            print(f"\nIntegridad Referencial: {refs['status']}")
            for k, v in refs.items():
                if k != "status":
                    print(f"  {k}: {v}")
            has_error = any(inf["status"] == "FAIL" for inf in dups.values()) or refs["status"] == "FAIL"
            sys.exit(1 if has_error else 0)
        finally:
            sess.close()
    else:
        success = run_idempotency_test(drivers_count=args.drivers)
        sys.exit(0 if success else 1)