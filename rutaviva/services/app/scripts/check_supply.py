from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from services.app.models.fleet import Driver, License, Sanction, Vehicle, VehicleState
from services.app.crud.fleet import get_available_supply, get_available_vehicles

POSTGRES_URL = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"

engine = create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def audit_real_postgres_supply():
    db = SessionLocal()
    try:
        eval_date = date.today()
        
        print("\n" + "="*115)
        print(f"🔍 AUDITORÍA DE OFERTA REAL (CONDUCTORES + VEHÍCULOS) EN POSTGRESQL (Fecha: {eval_date})")
        print("="*115)

        query = text("""
            SELECT d.driver_id, d.full_name, d.status AS driver_status,
                   v.plate, vs.status AS vehicle_status
            FROM driver d
            LEFT JOIN vehicle v ON d.driver_id = v.driver_id
            LEFT JOIN vehicle_state vs ON v.vehicle_id = vs.vehicle_id
        """)
        result = db.execute(query).fetchall()
        
        available_supply = get_available_supply(db, query_date=eval_date)
        available_vehicles = get_available_vehicles(db, query_date=eval_date)
        available_ids = {str(d.driver_id) for d in available_supply}

        for row in result:
            d_id, full_name, db_status, plate, v_status = row[0], row[1], row[2], row[3] or "SIN AUTO", row[4] or "N/A"
            d_id_str = str(d_id)
            is_available = d_id_str in available_ids
            status_str = "✅ EN OFERTA" if is_available else "❌ EXCLUIDO"
            
            reason = ""
            if not is_available:
                license_obj = db.query(License).filter(License.driver_id == d_id).first()
                sanction_obj = db.query(Sanction).filter(
                    Sanction.driver_id == d_id,
                    Sanction.starts_on <= eval_date,
                    (Sanction.ends_on.is_(None)) | (Sanction.ends_on >= eval_date)
                ).first()
                
                reasons = []
                if license_obj and license_obj.expires_on < eval_date:
                    reasons.append(f"Licencia vencida ({license_obj.expires_on})")
                if sanction_obj:
                    reasons.append(f"Sanción ({sanction_obj.starts_on} a {sanction_obj.ends_on})")
                if db_status != 'active':
                    reasons.append(f"Driver: {db_status}")
                
                reason = f" -> {', '.join(reasons)}"

            print(
                f"Placa: {plate:<10} (Auto: {v_status:<9}) | "
                f"Conductor: {full_name:<20} (Driver: {db_status:<9}) | "
                f"RN-09: {status_str}{reason}"
            )

        print("="*115)
        print(f"📊 Conductores disponibles: {len(available_supply)}/{len(result)} | Vehículos habilitados por RN-09: {len(available_vehicles)}\n")

    except Exception as e:
        print(f"❌ Error al consultar la base de datos real: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    audit_real_postgres_supply()