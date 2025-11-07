import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from src.core.config import settings
from src.core.logger import logging
from src.constants import MODEL_MAX_LENGTH, MODEL_BATCH_SIZE

# =========================================================
# MODEL INITIALIZATION (Same as before)
# =========================================================
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
# BULK SENTIMENT ANALYSIS (with MINI-BATCHING)
# =========================================================
def analyze_all_articles_in_bulk(all_jobs: list):
    """
    Analyzes all articles and their mentioned startups in bulk,
    using mini-batches to prevent OOM errors.

    Args:
        all_jobs (list): [
            {"article": article_row, "startups_to_analyze": [startup_info, ...]},
            ...
        ]
    
    Returns:
        list: DB-ready sentiment records
    """
    if not all_jobs:
        return []

    # 1. Build the list of all pairs (same as before)
    all_pairs = []  # Will store (text, hypothesis, articleId, startupId)
    labels = ["positive", "neutral", "negative"]
    
    for job in all_jobs:
        article = job["article"]
        text = f"{article.get('title', '')}. {article.get('content', '')}"
        
        for startup in job["startups_to_analyze"]:
            for label in labels:
                hypothesis = f"the news for {startup['name']} is {label}"
                all_pairs.append((text, hypothesis, article["id"], startup["id"], label))

    if not all_pairs:
        return []

    logging.info(f"Total items to predict: {len(all_pairs)}. Starting mini-batch processing...")

    # 2. Process in mini-batches
    all_entailment_scores = []
    
    batch_size = MODEL_BATCH_SIZE 
    total_batches = (len(all_pairs) + batch_size - 1) // batch_size

    try:
        for i in range(total_batches):
            logging.info(f"Processing batch {i+1}/{total_batches} (size {batch_size})...")
            start_index = i * batch_size
            end_index = min((i + 1) * batch_size, len(all_pairs))
            
            batch_pairs = all_pairs[start_index:end_index]
            
            batch_texts = [p[0] for p in batch_pairs]
            batch_hypotheses = [p[1] for p in batch_pairs]

            inputs = tokenizer(
                batch_texts,
                batch_hypotheses,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=MODEL_MAX_LENGTH
            ).to(device)

            with torch.no_grad():
                logits = model(**inputs).logits
                probs = F.softmax(logits, dim=1)
                entailment_scores_batch = probs[:, 0].cpu().numpy().tolist()
                
            all_entailment_scores.extend(entailment_scores_batch)
            
            del inputs, logits, probs
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    except Exception as e:
        logging.error(f"Mini-batch prediction failed: {e}")
        raise 

    logging.info("All mini-batches processed. Aggregating results...")

    # 3. Aggregate results (same as before)
    results_map = {}  # { (articleId, startupId): { "positiveScore": 0.0, ... } }
    
    for score, pair in zip(all_entailment_scores, all_pairs):
        article_id = pair[2]
        startup_id = pair[3]
        label = pair[4]
        
        key = (article_id, startup_id)
        if key not in results_map:
            results_map[key] = {}
        
        results_map[key][label + "Score"] = round(float(score), 4)

    # 4. Format for DB insertion (same as before)
    db_records = []
    for (article_id, startup_id), scores in results_map.items():
        # Handle cases where a label might be missing if a batch fails (though we raise error)
        # More importantly, handles the score lookup safely.
        positive_score = scores.get("positiveScore", 0.0)
        neutral_score = scores.get("neutralScore", 0.0)
        negative_score = scores.get("negativeScore", 0.0)
        
        # Determine best sentiment
        scores_dict = {
            "positive": positive_score,
            "neutral": neutral_score,
            "negative": negative_score
        }
        best_label = max(scores_dict, key=scores_dict.get)
        
        db_records.append({
            "articleId": article_id,
            "startupId": startup_id,
            "positiveScore": positive_score,
            "neutralScore": neutral_score,
            "negativeScore": negative_score,
            "sentiment": best_label
        })

    logging.info(f"Generated {len(db_records)} sentiment entries from bulk analysis.")
    return db_records