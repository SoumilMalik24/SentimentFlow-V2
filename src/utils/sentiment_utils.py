import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from src.core.config import settings 
from src.core.logger import logging 
from src.constants import MODEL_MAX_LENGTH

# =========================================================
# MODEL INITIALIZATION
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
# BULK SENTIMENT ANALYSIS (NEW)
# =========================================================
def analyze_all_articles_in_bulk(articles_with_startups: list):
    """
    Analyzes all articles and their found startups in a single model call.

    Args:
        articles_with_startups (list): 
            A list of tuples: [(article_row, list_of_startups), ...]
            e.g., [
                ( {"id": "a1", "title": "...", "content": "..."}, [{"id": "s1", "name": "Swiggy"}] ),
                ( {"id": "a2", "title": "...", "content": "..."}, [{"id": "s1", "name": "Swiggy"}, {"id": "s2", "name": "Zomato"}] )
            ]
    
    Returns:
        list[dict]: A flat list of DB-ready sentiment records.
    """
    if not articles_with_startups:
        logging.info("No articles to analyze in bulk.")
        return []

    logging.info(f"Building one giant batch for {len(articles_with_startups)} articles...")

    labels = ["positive", "neutral", "negative"]
    
    # These lists will hold all data for the single model call
    all_premises = []     # All article texts
    all_hypotheses = []   # All hypotheses
    all_mappings = []     # Tuples to map results back: (articleId, startupId, label)

    for article_row, startups_to_analyze in articles_with_startups:
        article_text = f"{article_row.get('title', '')}. {article_row.get('content', '')}"
        article_id = article_row["id"]

        for startup in startups_to_analyze:
            startup_id = startup["id"]
            startup_name = startup["name"]
            
            for label in labels:
                all_premises.append(article_text)
                all_hypotheses.append(f"the news for {startup_name} is {label}")
                all_mappings.append((article_id, startup_id, label))

    if not all_premises:
        logging.info("No startup/article pairs to analyze.")
        return []

    logging.info(f"Calling model ONCE with a total batch size of {len(all_premises)}...")

    try:
        # Tokenize and predict in one go
        inputs = tokenizer(
            all_premises,
            all_hypotheses,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=MODEL_MAX_LENGTH
        ).to(device)

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = F.softmax(logits, dim=1) 
            entailment_scores = probs[:, 0].cpu().numpy().tolist()

        # =========================================================
        # Process the single batch of results
        # =========================================================
        
        # 1. Aggregate scores
        # This dict will look like: { (articleId, startupId): { "positiveScore": 0.9, ... } }
        aggregated_scores = {}

        for (article_id, startup_id, label), score in zip(all_mappings, entailment_scores):
            key = (article_id, startup_id)
            if key not in aggregated_scores:
                aggregated_scores[key] = {}
            
            aggregated_scores[key][label + "Score"] = round(float(score), 4)

        # 2. Format for database
        db_records = []
        for (article_id, startup_id), scores_dict in aggregated_scores.items():
            # Determine best sentiment
            best_label = max(labels, key=lambda x: scores_dict[x + "Score"])
            
            db_records.append({
                "articleId": article_id,
                "startupId": startup_id,
                "positiveScore": scores_dict["positiveScore"],
                "neutralScore": scores_dict["neutralScore"],
                "negativeScore": scores_dict["negativeScore"],
                "sentiment": best_label
            })
        
        logging.info(f"Generated {len(db_records)} total sentiment entries from bulk analysis.")
        return db_records

    except Exception as e:
        logging.error(f"Bulk prediction failed: {e}", exc_info=True)
        return []
