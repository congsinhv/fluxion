// Fluxion commit message convention — see docs/code-standards.md §6.1.
// Format: `[#<ticket>]: <subject>` (imperative, lowercase first word, <= 72 chars).
// Exception: `[chore]: <subject>` for no-ticket commits.

const HEADER_RE = /^\[(#\d+|chore)\]: .+$/;

/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  plugins: [
    {
      rules: {
        "fluxion-header": (parsed) => {
          const header = parsed.header ?? "";
          if (!HEADER_RE.test(header)) {
            return [
              false,
              "Header must match `[#<ticket>]: <subject>` (or `[chore]: <subject>`). Example: `[#29]: scaffold monorepo`",
            ];
          }
          return [true];
        },
      },
    },
  ],
  rules: {
    "fluxion-header": [2, "always"],
    "header-max-length": [2, "always", 72],
    "body-leading-blank": [2, "always"],
    "footer-leading-blank": [2, "always"],
  },
  helpUrl: "https://github.com/congsinhv/fluxion/blob/main/docs/code-standards.md#61-commit-message-format",
};
