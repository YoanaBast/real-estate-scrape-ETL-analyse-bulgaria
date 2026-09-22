
## Expected Databricks file locations
this is my structure, you may need to change locations in the scrapers and the notebook

<pre>
  DATABRICKS
│
├── 📁 Workspace
│   └── 📓 [Databricks notebook]
│       
│
├── 🗄️ Catalog
│   └── workspace
│       └── default
│           └── Tables
│               ├── bronze_imot_listings
│               ├── bronze_imot_price_history
│               ├── silver_imot_listings
│               ├── silver_imot_price_history
│               ├── gold_agency_summary
│               ├── gold_market_by_location
│               └── gold_price_changes
│
└── 💾 Volumes
    └── /Volumes/workspace/default/real-estate/
        │
        ├── 📄 requirements.txt
        │
        ├── 📁 code/
        │   ├── imot_bg_sitemap_discovery.py
        │   ├── imot_bg_scraper.py
        │   └── imot_bg_test_fetch.py
        │
        ├── 📁 raw/
            ├── discovered_listing_urls.json
            ├── detail_snapshot.jsonl
            └── price_history.jsonl
        
</pre>
