from crud import (
    create_stock,
    delete_stock,
    get_stock_by_id,
    get_stock_by_symbol,
    list_stocks,
    search_stocks,
)
from database import SessionLocal

TEST_SYMBOL = "ZZTEST"

with SessionLocal() as db:
    print("1. Create a test stock")
    stock = create_stock(
        db, TEST_SYMBOL, company_name="Test Company", exchange="TEST", sector="Testing"
    )
    print("   created:", stock.stock_id, stock.symbol, stock.company_name)

    print("2. Creating the same symbol again must not duplicate it")
    again = create_stock(db, "  zztest ")
    print("   same id:", again.stock_id == stock.stock_id)

    print("3. Get by symbol (lowercase input)")
    found = get_stock_by_symbol(db, "zztest")
    print("   found:", found.symbol if found else None)

    print("4. Get by id")
    by_id = get_stock_by_id(db, stock.stock_id)
    print("   found:", by_id.symbol if by_id else None)

    print("5. Search 'test company'")
    results = search_stocks(db, "test company")
    print("   results:", [s.symbol for s in results])

    print("6. List stocks")
    print("   count:", len(list_stocks(db)))

    print("7. Delete the test stock")
    print("   deleted:", delete_stock(db, TEST_SYMBOL))
    print("   still exists:", get_stock_by_symbol(db, TEST_SYMBOL) is not None)

print("\nCRUD test finished.")