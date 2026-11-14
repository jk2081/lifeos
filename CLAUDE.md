# Life OS

This repo will hold `lifeos`, a Frappe v16 app. It is empty apart from the spec and mockups.

- **Read `SPEC.md` in full before writing any code.** It is the single source of truth. Where a later section overrides an earlier table, the spec says so.
- **Match the mockups in `mockups/`.** PNGs show the approved look. `mockups/source/` holds the HTML they were rendered from, for exact colours, sizes and spacing. That HTML uses a design-tool template format and is reference only; do not copy its structure into the app.
- **Build on a local bench, never on a live site.** Use Docker for Frappe v16 and a throwaway test site.
- **Follow the milestone order in section 14.** Finish each milestone with its tests passing, commit with the milestone number in the message, and update `STATUS.md`.
- **Record every deviation from the spec in `DECISIONS.md`**, with the reason.
- **Never write secrets** to the repo, logs or docs.
- The spec contains the owner's personal goals as seed data. Keep this repo private.
