# FABLE REVIEW BRIEF - launch readiness for the KY Box photo pipeline and the shooting process

You are the final reviewer before we shoot ~300-400 more boxes and publish them on kybox.com.
This is a REVIEW. Do not edit, move, rename or delete any existing file. Write only your report to
`PHOTOS\_review\FABLE_REVIEW_REPORT.md` (and any images you make for it into `PHOTOS\_review\`).

Goal we are held to: every photo must come out studio quality "right the first time, every time" with no per-photo handling.

## Read EVERY line of these (do not skim, do not sample)
- `site\tools\post_edit.py` (the image engine), `run_batch.py`, `finalize.py`, `process_all.py`, `make_review.py`, `make_masks.py`
- `site\tools\WORKHORSE.md` (the instructions a cheaper model follows to launch the run), `overrides.json`
- `PHOTOS\README.txt`, every file in `_work\meta\*.json` (45 projects: slug, title, box_style, industry, roles, alt text)
- Backups in `_work\post_edit_v*_backup.py` only to see what changed between versions
Report what each stage actually does, in plain words, and anything that disagrees with what the docs say it does.

## Look at EVERY image
- All finals in `PHOTOS\2-DONE\*\*.jpg`, `-cut.png` (check on a colored background for edge halos), and `-wide.jpg`
- Originals in `PHOTOS\1-ORIGINALS\*\` next to their finals, so you can judge what the pipeline changed
- Masks in `_work\masks\*\*.png` against their originals
For every project, list the angles we have (hero 3/4, front, open, insert, finish, set) and the angles that are MISSING for a good gallery.
Judge each final on: edges (any lost corner, scallop, halo, stray strip, jagged top), exposure (pale boxes too dark, dark boxes too bright, blown whites, crushed blacks), color (blue/cyan bounce from the blue backdrop on white, cream, silver or glossy black surfaces; muddy or over-saturated color; wrong cast), sharpness and over-processing (posterization, halos, crunchy clarity), shadow and framing (about 80% framing, centered, shadow natural, nothing clipped).

## Cover every base in the code
- Bugs and crashes: numpy vs Python types in JSON (we hit one), partial or corrupted `report.json` if a run is killed mid-write (we hit one), resume behavior, timeouts, Windows paths, Python 3.14 compatibility, missing-file handling, name collisions.
- Silent failures: a photo that is processed but wrong and still marked "done"; QC thresholds that are too loose or too strict; the AI mask path falling back to the older color-rule path without telling anyone.
- Order of operations in `run()`: white balance, mask, smoothing, despill, edge decolor, pale cast fix, glossy-black fix, light-surface haze fix, dust, tone (`flatten`), `pop`, `polish`, `edge_define`, composite, wide hero. Is each step safe on EVERY box type (white, cream, silver, glossy black, velvet flock, pastel blue, navy, red, orange, clear windows, foil)? Name any box type where a filter could damage real artwork and say how to detect it.
- Intake flow: loose photos in `PHOTOS\0-DROP` -> Claude sorts into `1-ORIGINALS\<slug>` -> meta JSON -> `make_masks.py` (needs rembg, runs on the Linux side only) -> `process_all.py` on Windows. Find every place this can break or be done in the wrong order, and every step that depends on a person remembering something.
- Output spec: file names `<slug>-NN-<role>.jpg`, `-cut.png`, `-wide.jpg`, sidecar `<slug>.json`, enums for industry / box_style / role, alt text quality, duplicate slugs against `site\projects\catalog.json` (do not modify it).

## Cover every base in the shooting process
Write a one-page SHOOTING PROTOCOL a person can follow at the booth, covering every box type we make (rigid set-up, two-piece, neck, book-style, clamshell, slipcase-drawer, magnetic; white, cream, silver, glossy black, velvet, pastel, saturated colors; windowed boxes; foil and emboss):
- backdrop choice per box color (current rule: matte blue by default, white or light backdrop only for blue or navy boxes), what to do for boxes that match every backdrop
- camera: regular 1x lens not portrait mode, locked white balance and exposure, distance, height, tripod, resolution, file format
- lighting: even, diffused, no glare; how to handle glossy or laminated panels (white card above and in front so the gloss mirrors white, not the dark or blue enclosure; or tilt about 10 degrees)
- the exact shot list per box, in order, with the role each shot will get (hero 3/4, front, back, side, open, insert, finish close-up, set)
- framing and margins (centered, space on all sides so nothing clips), box placement, keeping the base clean, no fingerprints or dust
- how to name or group the shots so sorting is automatic
- a pre-flight checklist and a 30-second check of the first processed result before shooting the rest of a batch

## Output format (keep it scannable)
1. VERDICT: ready to shoot at scale? yes / yes-with-fixes / no, in two sentences.
2. BLOCKERS: things that must be fixed before launch, each with file and line, what goes wrong, a concrete failing example, and the exact fix.
3. SHOULD FIX: next tier, same format.
4. NICE TO HAVE.
5. PER-PROJECT TABLE: project, shots we have, missing angles, edge / exposure / color grade (pass or fail), reshoot needed (exact photo names and why).
6. THE SHOOTING PROTOCOL (one page).
7. WHAT YOU DID NOT CHECK, and why.
Be specific and cite files, lines and photo names. If you are unsure, say so instead of guessing.
