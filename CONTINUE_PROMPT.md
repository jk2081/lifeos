An earlier run of this build stopped before it finished. Nobody is watching this run. Do not ask questions and do not wait for input.

Read CLAUDE.md, STATUS.md, DECISIONS.md and the git log, then SPEC.md. Check that the local bench and test site still work, and repair them if not.

Continue the build from the first milestone in section 14 of SPEC.md that is not finished. Follow the same rules as START_PROMPT.md, including its steps 2 to 7: commit after each milestone, keep STATUS.md current, create BUILD_DONE when everything is finished, or BUILD_BLOCKED with the reason if you cannot go further.

This machine already runs other Docker containers, including a Frappe Manager stack (`fm_global-nginx`, `fm_global-db`) that holds ports 80 and 443. Do not stop, restart, remove or change any container, image, volume or network that you did not create in this build. Prefix everything you create with `lifeos-`. Use ports other than 80, 443 and 3306 on the host. Docker has about 4 GB of memory unless the owner raised it, so keep the stack small: one bench container with its database and Redis, and no parallel heavy jobs.
