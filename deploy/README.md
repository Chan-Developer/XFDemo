# Deploy (Docker Compose)

This folder centralizes *deployment packaging* for XFDemo:

- `Dockerfile.backend`: backend image build
- `Dockerfile.frontend`: frontend image build
- `nginx.conf`: frontend nginx template (envsubst `BACKEND_ORIGIN`)
- `docker-compose.yml`: stack compose file (frontend + backend)
- `.env.deploy`: compose env template

Typical flow:

1. Build and export images into `output/deploy/images/`:
   `bash scripts/package_stack.sh`
2. Keep compose and environment configuration in `deploy/`.
3. Upload both image archives plus `deploy/docker-compose.yml` and
   `deploy/.env`, then load the images and start the stack.

Or do it in one command:

`bash scripts/deploy_remote.sh user@host /path/to/deploy`

Backend prompts and inspection rules are versioned under
`backend/modules/inspection/`; rebuild the backend image after changing them.
