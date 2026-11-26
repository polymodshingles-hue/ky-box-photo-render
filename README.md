# KY Box photo render

This workhorse creates local studio images from filed phone photos. It writes finals under `PHOTOS/2-DONE/<project>` and spins under `PHOTOS/3-SPIN/<project>`.

1. File originals and classify the project in `_work/meta/<project>.json`.
2. On the machine with rembg, run `python site/tools/make_masks.py PROJECT`. Copy the resulting PNG masks to the same relative location on the workhorse.
3. Run `python site/tools/process_all.py PROJECT` on Windows. Omit the project to process all filed projects.

Each included photo gets a 2400×2400 JPEG, WebP and transparent PNG, plus a 3200×1800 wide JPEG. The sidecar maps each final to its original. See [Workhorse instructions](site/tools/WORKHORSE.md) for dependencies, intake, mask migration, quality checks and recovery.

Use `python site/tools/build_spin.py PROJECT FRAMES_DIR MASKS_DIR` for a spin. Supply full, oriented frame masks named after numerically indexed frames such as `f_001.jpg` and `f_001.png`.

Run `python tests/check_meta.py` and `python -m unittest discover -s tests` for the metadata and synthetic regression checks. [Implementation handoff](WORKHORSE_HANDOFF.md).
