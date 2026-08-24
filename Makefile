.PHONY: dev-api dev-worker dev-web migrate test lint clean-data backup

dev-api:
	cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

dev-worker:
	cd backend && celery -A app.worker:celery_app worker --loglevel=INFO --concurrency=2

dev-web:
	cd frontend && npm run dev

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest && cd ../frontend && npm test -- --run

lint:
	cd backend && ruff check . && mypy app && cd ../frontend && npm run lint && npm run typecheck

clean-data:
	docker compose exec postgres psql -U lidoskop -d lidoskop -c "TRUNCATE companies, people, search_jobs CASCADE;"

backup:
	docker compose exec -T postgres pg_dump -U lidoskop -d lidoskop -Fc > backups/lidoskop.dump
