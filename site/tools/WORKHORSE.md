# Run a local photo batch

## Set up the batch

Use Python 3.14 on the Windows workhorse with `python -m pip install numpy opencv-python-headless Pillow`. Run commands from the repository root. The mask-producing machine also needs a working CPU installation of rembg and the isnet-general-use model.

1. Keep loose items in `PHOTOS/0-DROP` until identified. File photos under `PHOTOS/1-ORIGINALS/PROJECT`. Create `_work/meta/PROJECT.json` with the matching slug, original filenames, roles and alt text. A null role explicitly excludes that take. The reviewed workflow inventories video for a separate spin job.
2. On the mask machine, run `python site/tools/make_masks.py PROJECT`. Transfer its PNGs under `_work/masks/PROJECT`. **Regenerate pre-v17 masks once.** The new PNGs identify the exact source JPEG by SHA-256. Copy originals byte-for-byte between machines. Resaving either the original or the mask in an image editor can require regeneration.
3. On Windows run `python site/tools/process_all.py PROJECT`. Omit PROJECT for a full batch. All four variants are required for every tagged, included photo. Legacy `wide` flags may remain in manifests.
4. Return the exit code and all PENDING, CHECK, ERROR and HOLD lines. Exit 0 means completion. Exit 3 means a photo, project or intake item needs attention. A fatal stage error exits unsuccessfully. A held project keeps its previous delivery. Read `_work/pending.json` for outstanding intake and review the white and dark sheets under the printed review folder.

## Capture and color

Use matte blue by default, a light backdrop for navy or blue, and a white reflection card for glossy stock. Lock exposure and white balance. Include a neutral reference once per lighting setup. Keep headroom in foil highlights and inspect printed lettering for focus.

The default grade preserves captured product tone. White balance on neutral stock is chromatic only. Project-wide settings belong in `render_defaults` in the project manifest. Photo overrides in `site/tools/overrides.json` use `PROJECT/filename.jpg` keys and take precedence. Use `neutral_rgb` for a measured, valid neutral reference. Use `tone: "auto"` or `"white"` to opt into the creative grade. Capture, cream, navy and silver retain the capture grade. Never use a colored surface as a neutral reference.

Set `confirmed_neutral_stock` only for verified, unprinted neutral stock with backdrop spill. Use `see_through` to preserve a real window. Enable `straight_closed_edges` only for a known convex piece with reflection notches, and `square_tips` only for genuinely square corners. Dust removal is opt-in through `dust_cleanup`. Keep explicit repair rectangles small. A known printed detail may use a normalized `focus_rect` and a locally calibrated `focus_min`. Plain stock cannot serve as a focus target.

## Review and recovery

The AI-outline support threshold is provisional. Check low-contrast materials against a traced edge. Compare the transparent PNG on dark and light backgrounds at 100%. Check the wide hero for ground contact and clear left-side space. Holds reserve their original slot among the sorted role-tagged photos. Changes to the role list can change numbering.

One writer owns the batch. Retry the same command after interruption. A failed promotion preserves the previous complete folder under `_work/previous`; rerunning restores it when the final name is absent. Local finalization validates input identity and all four rendered files. The website and catalog are outside the delivery workflow.

Before bulk work, process one local reference batch containing silver foil, cream stock with pale-blue print, navy on a light backdrop, glossy stock with the white card, a real window and a detached lid. Reuse the same captures to compare versions. Record wall time, peak memory, holds and manual repairs on the actual two-core machine. Track usable photos per hour.
