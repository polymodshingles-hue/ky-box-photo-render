PHOTOS - how this is organized (do not rename these folders)

0-DROP        New phone photos land here, loose. Claude sorts them into projects.
1-ORIGINALS   Original photos, one folder per project. NEVER edited or deleted. Pipeline only reads from here.
2-DONE        Finished, spec-named photos per project (<slug>-NN-role.jpg/.webp, -cut.png, -wide.jpg, <slug>.json). Only this goes to the website.
_tests        Old test shots (blue/gray/green backdrop tests). Ignore.

Run: python site/tools/process_all.py   (reads 1-ORIGINALS, writes 2-DONE; scratch lives in _work)
