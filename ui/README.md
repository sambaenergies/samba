# SAMBA UI

Vue 3 + TypeScript + Vite frontend for SAMBA, supporting both web and native desktop (Tauri) modes.

## Quick Start

1. Install dependencies:

```bash
npm install
```

2. Run web dev mode:

```bash
npm run dev
```

3. Run native desktop mode (spawns `samba serve` side process):

```bash
npm run tauri:dev
```

## Build

```bash
npm run build
npm run tauri:build
```

## Quality Gates

```bash
npm run lint
npm run test
npm run test:e2e
```

If Playwright browsers are missing, install once:

```bash
npx playwright install chromium
```

## Notes

- Web mode uses configured backend URL from Settings.
- Tauri mode receives backend URL from Rust side via `samba-ready` event.
- Results dashboard reads artifacts from `/api/v1/jobs/:runId/artifacts/:filename`.
