## Documentation (four live documents, flows and technology kept apart)

- `docs/FLOWS.md` says what happens and what the person does, with no technology (the linter fails it on technology terms). `docs/TECH.md` says what it is made of, why, and how to extend it. `docs/OPERATIONS.md` is install, run, update and fix. `docs/ROADMAP.md` is status, open items, decisions for the owner and what is not verified. `README.md` is the start and the map; `CHANGELOG.md` is per version; evidence lives in `docs/history/`.
- One fact has one home: state it once, link to it elsewhere. Update the documents in the same commit as the code (the change-to-document map is in `skills/docs-generation/references/restructure-and-update.md`).
- Name states, buttons and settings exactly as the code does. Reference code by path and symbol, never by line number.
- Run `<!-- FILL: the lint command, for example ./tool test lint -->` before committing; it checks commands, links, anchors, paths, markers and the flows/technology split.
- Say what was verified and what was not. Anything never run against the real system goes under "Not verified" in `docs/ROADMAP.md`.
