"""Run a complete local batch under one writer lock."""
import sys

from pipeline import writer
import run_batch
import make_review
import finalize


def main(selected):
    with writer():
        batch = run_batch.run(selected)
        delivery = finalize.run(selected)
        make_review.run(selected)
    if batch or delivery:
        print('Incomplete batch. See PENDING, HOLD, CHECK and ERROR entries above.')
        return 3
    print('ALL STEPS DONE. Local finals in PHOTOS/2-DONE. Sheets in _work/processed/reviews.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
