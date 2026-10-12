import sys
import time

from crud import add_sentiments, count_unscored_news, get_unscored_news
from database import SessionLocal
from sentiment import build_text, score_texts

BATCH = 64  # articles scored and saved together

# Usage:  python score_news.py 200     (score up to 200 unscored articles)
#         python score_news.py ALL     (score everything that is left)
arg = sys.argv[1].upper() if len(sys.argv) > 1 else "200"
limit = None if arg == "ALL" else int(arg)

started = time.time()
done = 0

with SessionLocal() as db:
    print(f"Articles waiting for a score: {count_unscored_news(db)}")

    while limit is None or done < limit:
        size = BATCH if limit is None else min(BATCH, limit - done)
        rows = get_unscored_news(db, limit=size)
        if not rows:
            break

        texts = [build_text(r.title, r.description) for r in rows]
        results = score_texts(texts)
        done += add_sentiments(db, [(r.news_id, res) for r, res in zip(rows, results)])

        rate = done / (time.time() - started)
        print(f"  scored {done}  ({rate:.1f} articles/second)")

    remaining = count_unscored_news(db)

print(f"\nScored {done} articles in {time.time() - started:.0f} seconds. Still unscored: {remaining}")
