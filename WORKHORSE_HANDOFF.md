# Photo workhorse v17 handoff

Implemented on PR #4, branch `full-review-v2`. The review baseline was `fa8da3a`. Changes are limited to the local rendering and review workflow.

## Delivery and intake

- Each included take produces a 2400×2400 JPEG, WebP, RGBA cutout and a 3200×1800 wide JPEG. The sidecar includes original filename, role, alt text and project notes. A held take retains its numbering slot. Numbering still follows the sorted role list when that list is edited.
- Loose items, filed videos and unclassified filenames appear in `_work/pending.json`. An explicit null role means EXTRA. A new unclassified source blocks replacement of that project's finals. Intake inventory leaves originals where they were filed. A person still identifies projects and decides how to extract spin frames from video.
- Source, mask, render settings and output hashes govern resume. The whole local batch holds one writer lock. Standalone stages take the same lock. Staging is outside the delivery tree. Finalization checks all four hashes, decodes each staged file, verifies dimensions and PNG alpha, then promotes the complete project. One previous version per project is retained for recovery. Unchanged finals and matching review sheets are reused.
- Removed the legacy website/catalog writers and abandoned debug drivers. Photo overrides now use project-qualified keys. The 45 checked-in string approval values became JSON null because the repo contained no independent confirmation of brand permission. A verified decision can be recorded as true or false.

## Image and spin changes

- New mask PNGs include the source JPEG SHA-256 and model name. Mask generation starts inference only when needed and resumes without a time cutoff. A same-sized mask on empty backdrop can now trigger CHECK through source-boundary support. The threshold is provisional.
- The default grade preserves capture tone. Neutral white balance no longer jumps at backdrop value 215. Interior spill correction, dust inpainting, creative tone grading and geometric reconstruction are explicit choices. The default edge path avoids whole-outline growth and erosion. It limits edge repainting on colored backdrops to one working pixel. Known windows can preserve holes and known straight glossy edges can enable hull repair.
- Local edge-color estimation uses a lower resolution while keeping full-resolution edge decisions. Compositing uses float32 and broadcasting. Simulated shadow is confined to the floor contact band. Exports carry an sRGB profile. JPEGs use full chroma resolution. Optional focus checks require a calibrated, known printed detail.
- Spins use numerically ordered, oriented full frames and matching full-frame masks. A common crop includes all angles, windows and separate lids survive the mask pass, and a failed rebuild preserves the prior viewer. Spin grading defaults to captured color. A project neutral reference can be shared with the stills. Review sheets include white masters and dark-ground cutouts.

## Verification

- Local Windows run: all ten synthetic regression tests passed, including real CLI rendering/finalization and spin builds, two-process lock contention, wrong-mask QC, corrupt scratch files, rollback, unclassified intake, legacy mask migration, resume and HOLD numbering. The mask-producer test stubs inference and exercises the real producer and PNG metadata path.
- All 45 project manifests passed validation. The checks workflow runs compilation, metadata checks and the regression suite on Windows and Ubuntu. Consult the checks on the PR for the current remote result.
- One controlled 4000×3000 synthetic render with two OpenCV threads and precomputed masks took 12.26 s at the review baseline and 3.88 s on the revised engine during development. Both wrote all four files and passed their QC. The comparison includes different default processing. It excludes model inference, finalization and manual review.

## Next operator action

1. Use the PR branch on both machines. Regenerate old masks once with `python site/tools/make_masks.py PROJECT` on the rembg machine. Transfer PNGs without resaving them.
2. On the workhorse run `python site/tools/process_all.py PROJECT`. Check exit status, the pending inventory, and the printed review folder. Finals stay in `PHOTOS/2-DONE`.
3. Use a private reference batch with silver foil, cream and pale-blue print, navy on a light backdrop, white-card gloss, an open window, and a detached lid. Compare original and exports at 100% on light and dark grounds. Confirm known window and material settings. Measure elapsed time, peak memory, holds, rework and usable photos per hour.
4. Record the outcome before bulk processing. Production photography, actual rembg model inference and actual two-core throughput were unavailable in this checkout. No production files were processed or published.

[Operating instructions](site/tools/WORKHORSE.md) · [Regression tests](tests/test_pipeline.py)
