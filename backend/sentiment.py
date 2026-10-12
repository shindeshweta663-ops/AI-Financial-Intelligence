from typing import Dict, List, Optional

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_NAME = "ProsusAI/finbert"  # FinBERT trained on financial text
MAX_LENGTH = 256  # headline + short summary fits; keeps CPU runs fast

_tokenizer = None
_model = None


def _load():
    """Load the model once (the first call downloads it, about 400 MB)."""
    global _tokenizer, _model
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model.eval()  # inference mode, not training
    return _tokenizer, _model


def build_text(title: Optional[str], description: Optional[str]) -> str:
    """FinBERT reads the headline plus the summary when we have one."""
    parts = [(title or "").strip(), (description or "").strip()]
    return ". ".join(p for p in parts if p)


def score_texts(texts: List[str], batch_size: int = 16) -> List[Dict]:
    """Return one dict per text: sentiment label and the three probabilities."""
    tokenizer, model = _load()
    # Label order comes from the model itself, so we never hard-code it.
    labels = {index: name.lower() for index, name in model.config.id2label.items()}

    results: List[Dict] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        with torch.no_grad():
            probabilities = torch.softmax(model(**inputs).logits, dim=-1)

        for row in probabilities:
            scores = {labels[i]: float(row[i]) for i in range(len(labels))}
            results.append(
                {
                    "sentiment": max(scores, key=scores.get),
                    "positive_score": round(scores["positive"], 4),
                    "neutral_score": round(scores["neutral"], 4),
                    "negative_score": round(scores["negative"], 4),
                }
            )
    return results
