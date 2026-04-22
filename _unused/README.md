# _unused/ — quarantine folder

Files in this folder are **not served by Flask** and **not referenced by any
rendered template**. They were moved here during a cleanup pass after a
messy merge, instead of being deleted, so the team can review before
permanent removal.

## Contents

| File | Why it's here |
|---|---|
| `board.html` | Standalone HTML at repo root. Not rendered by any route. References `css/styles.css` and `images/*`. |
| `index.html` | Standalone HTML at repo root. `/` already renders `templates/itinerary.html`. |
| `login.html` | Standalone HTML at repo root. Duplicate name with the real `templates/login.html`. |
| `planner.html` | Standalone HTML at repo root. Not wired to any route. |
| `Popular.html` | Originally rendered by `/community`; replaced by `templates/community.html` in a later merge. |
| `styles.css` | Alternate design system (`--primary` palette, Inter font). Not loaded by any rendered template. The project's single stylesheet is `static/css/travelplan.css` (+ `static/css/community.css` for the community page). |

## Broken refs (expected)

These files reference old relative paths (`css/styles.css`, `images/*.png`)
that no longer resolve from this folder. That is fine — they are not meant
to be opened in a browser. If you want to view one, rename/copy it back
to its original location first.

## Safe to delete?

Once everyone on the team has confirmed none of this is salvageable,
delete the whole `_unused/` folder. Until then, leave it — `git log` on a
file tells you who wrote it and when, which is useful context when deciding.
