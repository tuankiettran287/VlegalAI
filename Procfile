web: python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
migrate: python -m alembic upgrade head
reindex: python scripts/sync_external_graphrag.py --reset-neo4j --reset-postgres
