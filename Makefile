.PHONY: up down logs ps test api-test agent-test ui-test config-test clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

test: api-test agent-test ui-test config-test

api-test:
	PYTHONPATH=services/control-api SENTINEL_DB_URL=sqlite:////tmp/sentinel-make-test.db pytest -q services/control-api/tests

agent-test:
	cd agents/sentinel-agent && go test ./...

ui-test:
	node --check services/web-ui/js/api.js
	node --check services/web-ui/js/ui.js
	node --check services/web-ui/js/app.js

config-test:
	python scripts/validate-config.py

clean:
	docker compose down -v --remove-orphans
