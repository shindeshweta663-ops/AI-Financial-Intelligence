import time

from sentiment import score_texts

samples = [
    "Company beats earnings expectations and raises full-year profit guidance",
    "Shares plunge after the company cuts its outlook and announces layoffs",
    "The company will hold its annual shareholder meeting on Thursday",
    "Regulators open investigation into accounting practices, stock falls sharply",
    "Record quarterly revenue driven by strong demand",
]

started = time.time()
results = score_texts(samples)
elapsed = time.time() - started

for text, r in zip(samples, results):
    print(
        f"{r['sentiment']:<9} pos={r['positive_score']:.2f} "
        f"neu={r['neutral_score']:.2f} neg={r['negative_score']:.2f}  |  {text[:60]}"
    )
print(f"\nScored {len(samples)} texts in {elapsed:.1f} seconds (includes model loading)")
