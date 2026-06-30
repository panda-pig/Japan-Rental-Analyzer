web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
release: python scripts/init_db.py && python scripts/seed_regions.py