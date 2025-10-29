# SentimentFlow-V2
Minor Project



Startup-News-Sentiment-v2/
│
├── .env
├── requirements.txt
├── main.py
└── src/
    ├── core/
    │   ├── __init__.py
    │   ├── config.py
    │   └── logger.py
    │
    ├── utils/
    │   ├── __init__.py
    │   ├── db_utils.py
    │   ├── api_utils.py
    │   ├── text_utils.py
    │   ├── sentiment_utils.py
    │   └── pipeline_utils.py
    │
    ├── pipeline/
    │   ├── __init__.py
    │   └── orchestrator.py
    │
    ├── sentiments/
    │   ├── __init__.py
    │   ├── sentiment_model.ipynb
    │   └── finbert_model/
    │
    └── constants/
        ├── __init__.py
        └── paths.py
