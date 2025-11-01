"""

Handles all sentiment analysis logic for the project using the
zero-shot startup sentiment model hosted on Hugging Face Hub.

Model: Soumil24/zero-shot-startup-sentiment-v2
Supports batch inference for multiple startups per article.
"""

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from src.core.logger import logging
from itertools import chain

# =========================================================
# MODEL INITIALIZATION
# =========================================================
MODEL_ID = "Soumil24/zero-shot-startup-sentiment-v2"
device = "cuda" if torch.cuda.is_available() else "cpu"

try:
    logging.info(f"Loading zero-shot sentiment model: {MODEL_ID}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    model.to(device)
    model.eval()
    logging.info(f"Model loaded successfully on {device.upper()}")
except Exception as e:
    logging.error(f"Failed to load sentiment model: {e}")
    raise


# =========================================================
# BATCH ZERO-SHOT SENTIMENT PREDICTION
# =========================================================
def predict_batch_for_startups(article_text: str, startups: list):
    """
    Runs batched zero-shot sentiment analysis for all startups mentioned in one article.

    Args:
        article_text (str): Full article text (title + content)
        startups (list): [{"id": str, "name": str}, ...]

    Returns:
        dict of startup_id -> sentiment info:
        {
            "startup_id": {
                "positiveScore": float,
                "neutralScore": float,
                "negativeScore": float,
                "sentiment": str
            }
        }
    """
    if not startups:
        return {}

    # Build all (premise, hypothesis) pairs
    labels = ["positive", "neutral", "negative"]
    texts, hypotheses, mapping = [], [], []

    for startup in startups:
        for label in labels:
            texts.append(article_text)
            hypotheses.append(f"The news is {label} for {startup['name']}.")
            mapping.append((startup["id"], label))

    try:
        # Tokenize everything together for one large batch
        inputs = tokenizer(
            texts,
            hypotheses,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=256
        ).to(device)

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = F.softmax(logits, dim=1)
            entailment_scores = probs[:, 0].cpu().numpy().tolist()

        # Aggregate scores per startup
        results = {}
        for (startup_id, label), score in zip(mapping, entailment_scores):
            if startup_id not in results:
                results[startup_id] = {lbl + "Score": 0.0 for lbl in labels}

            results[startup_id][label + "Score"] = round(float(score), 4)

        # Determine final sentiment for each startup
        for sid, data in results.items():
            best_label = max(["positive", "neutral", "negative"],
                             key=lambda x: data[x + "Score"])
            data["sentiment"] = best_label

        return results

    except Exception as e:
        logging.error(f"Batch prediction failed: {e}")
        return {}


# =========================================================
# ARTICLE SENTIMENT BATCH WRAPPER
# =========================================================
def analyze_article_sentiments(article: dict, startups: list):
    """
    Analyzes one article for multiple startups and returns DB-ready sentiment records.

    Args:
        article (dict): {"id": str, "title": str, "content": str}
        startups (list): [{"id": str, "name": str}, ...]

    Returns:
        list[dict]: Each dict is ready for DB insertion.
    """
    if not startups:
        return []

    text = f"{article.get('title', '')}. {article.get('content', '')}"
    article_id = article["id"]

    predictions = predict_batch_for_startups(text, startups)
    if not predictions:
        return []

    db_records = []
    for startup in startups:
        sid = startup["id"]
        if sid not in predictions:
            continue

        scores = predictions[sid]
        db_records.append({
            "articleId": article_id,
            "startupId": sid,
            "positiveScore": scores["positiveScore"],
            "neutralScore": scores["neutralScore"],
            "negativeScore": scores["negativeScore"],
            "sentiment": scores["sentiment"]
        })

    logging.info(f"Generated {len(db_records)} sentiment entries for article {article_id}")
    return db_records


# =========================================================
# COMBINED PIPELINE STEP (MODEL + DB)
# =========================================================
def predict_and_store_sentiments(conn, article, startups, db_insert_func):
    """
    Performs batch prediction for one article and stores results in DB.

    Args:
        conn: Active PostgreSQL connection
        article (dict): Article record with title/content/id
        startups (list): List of startup dicts
        db_insert_func (callable): db_utils.batch_insert_article_sentiments
    """
    try:
        sentiment_records = analyze_article_sentiments(article, startups)
        if not sentiment_records:
            logging.info(f"No startup sentiments found for article {article['id']}")
            return

        db_insert_func(conn, sentiment_records)
        logging.info(f"Stored {len(sentiment_records)} sentiment rows for article {article['id']}")

    except Exception as e:
        logging.error(f"Failed to process article {article.get('id')}: {e}")
