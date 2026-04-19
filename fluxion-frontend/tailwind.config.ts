// Tailwind v4: configuration lives in CSS (@theme block in src/index.css).
// This file exists for IDE integration and tooling that expects a config entry point.
// Do not add theme overrides here — use `@theme { }` in src/index.css instead.
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
};

export default config;
