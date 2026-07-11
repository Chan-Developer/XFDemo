# Deploy (Docker Compose)

This folder centralizes *deployment packaging* for XFDemo:

- `Dockerfile.backend`: backend image build
- `Dockerfile.frontend`: frontend image build
- `nginx.conf`: frontend nginx template (envsubst `BACKEND_ORIGIN`)
- `docker-compose.yml`: stack compose file (frontend + backend)
- `.env.deploy`: compose env template

Typical flow:

1. Build + export images into `deploy/`:
   `bash scripts/package_stack.sh`
2. Copy `deploy/` to a target machine, then:
   `docker load -i xf-backend-latest.tar`
   `docker load -i xf-frontend-latest.tar`
   `docker compose --env-file .env -f docker-compose.yml up -d`

Or do it in one command:

`bash scripts/deploy_remote.sh user@host /path/to/deploy`

Editing prompt without rebuilding:

This repo ships a `deploy/prompt.py` that is meant to be edited on the target machine.

1. Edit `prompt.py`
2. Restart backend:
   `docker compose -f docker-compose.yml restart xf-backend`
