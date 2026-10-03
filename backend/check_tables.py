from sqlalchemy import inspect

from database import engine

inspector = inspect(engine)
tables = sorted(inspector.get_table_names())

print(f"Found {len(tables)} tables in the database:\n")

for table in tables:
    print(f"TABLE: {table}")
    for column in inspector.get_columns(table):
        print(f"    {column['name']:<25} {column['type']}")
    print()