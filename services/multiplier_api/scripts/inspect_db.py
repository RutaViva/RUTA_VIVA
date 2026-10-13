# scripts/inspect_db.py
# Lista tablas y columnas de la base a la que apunta DATABASE_URL.
# Sirve para comprobar la conexión y alinear los modelos con el seed.
from sqlalchemy import inspect

from app.core.database import engine

inspector = inspect(engine)
for table in inspector.get_table_names():
    print(f"\n{table}")
    for column in inspector.get_columns(table):
        print(f"  - {column['name']}: {column['type']}")