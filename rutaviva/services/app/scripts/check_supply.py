from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from services.app.models.fleet import Driver, License, Sanction
from services.app.crud.fleet import get_available_supply

POSTGRES_URL = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"

engine = create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def audit_real_postgres_supply():
    db = SessionLocal()
    try:
        # Toma automáticamente la fecha actual del sistema
        eval_date = date.today()
        
        print("\n" + "="*95)
        print(f"🔍 AUDITORÍA DE OFERTA REAL EN POSTGRESQL (Fecha de evaluación: {eval_date})")
        print("="*95)

        result = db.execute(text("SELECT driver_id, full_name, status FROM driver")).fetchall()
        available_supply = get_available_supply(db, query_date=eval_date)
        
        available_ids = {str(d.driver_id) for d in available_supply}

        total_drivers = len(result)
        for row in result:
            d_id, full_name, db_status = row[0], row[1], row[2]
            d_id_str = str(d_id)
            is_available = d_id_str in available_ids
            status_str = "✅ DISPONIBLE (En la oferta)" if is_available else "❌ EXCLUIDO (Fuera de la oferta)"
            
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
                    reasons.append(f"Licencia expirada el {license_obj.expires_on}")
                if sanction_obj:
                    reasons.append(f"Sanción vigente ({sanction_obj.starts_on} a {sanction_obj.ends_on})")
                if db_status != 'active':
                    reasons.append(f"Estado en tabla: {db_status}")
                
                reason = f" -> Motivo: {', '.join(reasons) if reasons else 'Sin licencia registrada / Excluido por RN-09'}"

            print(f"ID: {d_id_str[:8]}... | Nombre: {full_name:<20} | Estado DB: {db_status:<9} | RN-09: {status_str}{reason}")

        print("="*95)
        print(f"📊 Resumen: {len(available_supply)} conductores disponibles de un total de {total_drivers} en la base de datos.\n")

    except Exception as e:
        print(f"❌ Error al consultar la base de datos real: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    audit_real_postgres_supply()