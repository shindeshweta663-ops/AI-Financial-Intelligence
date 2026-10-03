from sqlalchemy import func, inspect, select

import models  # noqa: F401  (importing registers all models on Base)
from database import Base, SessionLocal, engine

inspector = inspect(engine)
db_tables = set(inspector.get_table_names())
all_ok = True

print("Checking models against the real database...\n")

with SessionLocal() as session:
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table = model.__table__
        name = table.name

        if name not in db_tables:
            print(f"[MISSING TABLE] {model.__name__} -> {name}")
            all_ok = False
            continue

        db_columns = {c["name"] for c in inspector.get_columns(name)}
        model_columns = {c.name for c in table.columns}

        only_in_model = model_columns - db_columns
        only_in_db = db_columns - model_columns

        if only_in_model or only_in_db:
            print(f"[MISMATCH] {model.__name__} ({name})")
            if only_in_model:
                print("    in model but not in database:", sorted(only_in_model))
            if only_in_db:
                print("    in database but not in model:", sorted(only_in_db))
            all_ok = False
        else:
            row_count = session.execute(select(func.count()).select_from(model)).scalar()
            print(f"[OK] {model.__name__:<22} table={name:<24} rows={row_count}")

print()
print("All 12 models match the database." if all_ok else "Some models do not match. See above.")