Read CLAUDE.md, then SPEC.md from start to finish, then look at every image in mockups/.

Build the `lifeos` Frappe app described in SPEC.md, in this repository. Nobody is watching this run. Do not ask questions and do not wait for input.

1. Set up a local Frappe v16 bench with Docker and a test site. Keep the bench outside the tracked files or in a git-ignored folder. If Docker cannot be used at all, write the reason to a file named BUILD_BLOCKED and stop.
2. Work through milestones M0 to M9 in section 14 of SPEC.md, in order. After each one: run its tests, update STATUS.md, and commit with the milestone number in the message.
3. Follow the "Working rules for a single long run" in section 14. Use the defaults in section 15 and record them in DECISIONS.md.
4. After each front-end milestone, open the screens in a headless browser at 1440 px and 390 px wide, take screenshots, compare them with mockups/, and fix what is off.
5. If a command is refused by the permission system, do not retry it. Find another way, or record it in STATUS.md and move on.
6. When every milestone is finished and the acceptance list in section 13 has been checked, write STATUS.md with: what works, what is stubbed, what is untested, and the exact commands to install the app on an existing bench. Then create an empty file named BUILD_DONE and commit.
7. If you cannot make any further progress, write the reason to BUILD_BLOCKED, commit, and stop.
