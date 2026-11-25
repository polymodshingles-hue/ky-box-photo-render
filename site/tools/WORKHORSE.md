# WORKHORSE: run the photo pipeline (KY Box)

Your whole job: start ONE command, wait for it, and report its output. The script does all the image work. You do not judge, fix or tune images. Claude (the controller) does the quality check afterward.

## Do this
1. Open a terminal in `C:\Users\shawn\ky box`.
2. Run exactly: `python site/tools/process_all.py`
   (If you were told specific project folders, add them after it: `python site/tools/process_all.py blue-test`.)
3. It can take a long time (about 15 seconds per photo). If it gets cut off or times out, run the SAME command again. It resumes and skips finished photos.
4. When it prints `ALL STEPS DONE`, reply with the last 40 lines of its output. Nothing else.

Needs Python 3 with opencv-python, numpy, Pillow (`pip install opencv-python numpy pillow`) if an import error appears.

## Hard rules (no exceptions)
- Do NOT edit, create, move, rename or delete any file. Especially never `overrides.json`, any `.py` file, anything in `PHOTOS`, or `_work\meta`.
- Do NOT create other scripts, other output folders, or your own version of the pipeline. Outputs go only where the script puts them (`_work\processed` for scratch, `PHOTOS\2-DONE` for finals).
- Do NOT retry with different settings, do not "fix" photos, do not hold or skip photos yourself. The script decides and Claude handles anything it flags.
- Do NOT open or judge the images. Do NOT use AI image tools.
- If a command errors, copy the full error into your reply and stop. Do not try to repair it.
