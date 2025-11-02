import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from src.core.config import settings 
from src.core.logger import logging 
from src.constants import MODEL_MAX_LENGTH

# =========================================================
# MODEL INITIALIZATION
# =========================================================
# We use MODEL_PATH to load the ID from your settings
MODEL_ID = settings.MODEL_PATH 
device = "cuda" if torch.cuda.is_available() else "cpu"

try:
    logging.info(f"Loading zero-shot sentiment model: {MODEL_ID}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=settings.HF_TOKEN)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, token=settings.HF_TOKEN)
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
    """
    if not startups:
        return {}

    labels = ["positive", "neutral", "negative"]
    texts, hypotheses, mapping = [], [], []

    for startup in startups:
        for label in labels:
            texts.append(article_text)
            # This is the "hypothesis" you were building
            hypotheses.append(f"the news for {startup['name']} is {label}")
            mapping.append((startup["id"], label))

    try:
        inputs = tokenizer(
            texts,
            hypotheses,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=MODEL_MAX_LENGTH
        ).to(device)

        with torch.no_grad():
            logits = model(**inputs).logits
            # This is where we get the probabilities (F.softmax)
            probs = F.softmax(logits, dim=1) 
            
            # This is your "entail_scores" (probs[:, 0])
            entailment_scores = probs[:, 0].cpu().numpy().tolist()

        # Aggregate scores per startup
        results = {}
        for (startup_id, label), score in zip(mapping, entailment_scores):
            if startup_id not in results:
                results[startup_id] = {lbl + "Score": 0.0 for lbl in labels}

            # This is where we save the "positive", "neutral", and "negative" scores
            results[startup_id][label + "Score"] = round(float(score), 4)

        # Determine final sentiment for each startup
        for sid, data in results.items():
            best_label = max(labels, key=lambda x: data[x + "Score"])
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
        # This creates the final dictionary for the database
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