# fluxion-frontend

React 19 admin console for the Fluxion MDM platform.

## Stack

- **React 19** + **TypeScript 5** (strict)
- **Vite 5** — dev server and bundler
- **Tailwind CSS 4** — utility-first styling via `@tailwindcss/vite` plugin
- **shadcn/ui** — component primitives (installed on demand via `bunx shadcn add <component>`)
- **TanStack Router** + **TanStack Query** — routing and server state
- **AWS Amplify v6** — GraphQL client (wired in ticket #33)
- **Bun** — package manager and script runner
- **Vitest** + **Testing Library** — unit tests
- **ESLint 9** (flat config) + **Prettier 3** — linting and formatting

## Prerequisites

- [Bun](https://bun.sh/) >= 1.1
- Node 20+ (for tooling compatibility)

## Setup

```bash
bun install
```

## Scripts

| Script                  | Description                                    |
| ----------------------- | ---------------------------------------------- |
| `bun run dev`           | Start Vite dev server at http://localhost:5173 |
| `bun run build`         | Type-check then produce `dist/`                |
| `bun run preview`       | Serve the `dist/` build locally                |
| `bun run lint`          | ESLint — zero warnings tolerance               |
| `bun run format:check`  | Prettier check (CI gate)                       |
| `bun run format`        | Prettier write (auto-fix)                      |
| `bun run typecheck`     | `tsc --noEmit` strict check                    |
| `bun run test`          | Vitest unit tests (single run)                 |
| `bun run test:coverage` | Vitest with V8 coverage (80% threshold)        |
| `bun run test:e2e`      | Playwright E2E (wired in downstream ticket)    |

## Adding shadcn/ui components

```bash
bunx shadcn add button
bunx shadcn add dialog
```

Components are generated into `src/components/ui/`. Import via alias:

```ts
import { Button } from "@/components/ui/button";
```

## Source layout

Feature-based organization per [docs/module-structure.md §4](../docs/module-structure.md).

```
src/
├── features/        # Business features — devices, actions, chat, message-templates, tacs
├── components/ui/   # shadcn/ui primitives
├── hooks/           # Cross-feature hooks
├── lib/             # Shared utilities (cn helper, Amplify config stub)
├── services/        # API gateway / Amplify client wrappers
├── types/           # Shared TypeScript types (GraphQL-generated)
├── routes/          # TanStack Router route tree (stub)
├── App.tsx
└── main.tsx
```

## Path alias

`@/*` resolves to `src/*` in TypeScript, Vite, and Vitest.

## Tailwind v4 notes

Config is CSS-first: theme tokens live in `src/index.css` under `@theme { }`.
`tailwind.config.ts` exists for IDE integration only — do not add theme overrides there.

## References

- [docs/module-structure.md §4](../docs/module-structure.md) — frontend layout rules
- [docs/code-standards.md §4](../docs/code-standards.md) — TypeScript rules
