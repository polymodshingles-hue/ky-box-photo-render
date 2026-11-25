# KY Box photo render

Pipeline that turns phone photos of boxes into website-ready images (AI cutout, white or transparent background, wide hero) and 360 spins.

- `site/tools/process_all.py` : one command for photos (run_batch -> make_review -> finalize). See `site/tools/WORKHORSE.md`.
- `site/tools/post_edit.py` : the image engine (version in `ENGINE`).
- `site/tools/build_spin.py` : 360 spin builder (frames + masks in, web viewer out).
- `_work/meta/` : one JSON per project (title, style, industry, photo roles).
- `site/tools/overrides.json` : per-photo fixes (rect, trim, tone, keystone, skip).

Photos, masks and renders are not stored here (public repo). `python tests/check_meta.py` is the PR check for the meta files.
