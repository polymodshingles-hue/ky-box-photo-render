"""Synthetic production-entry-point regressions. All generated assets live in temp directories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, PngImagePlugin

TOOLS = Path(__file__).resolve().parents[1] / 'site/tools'
sys.path.insert(0, str(TOOLS))
import pipeline as F
import post_edit as engine
import build_spin


class ImageTests(unittest.TestCase):
    def test_mask_geometry_and_stock(self):
        mask = np.zeros((240, 320), np.uint8)
        mask[:70, :70] = 255
        np.testing.assert_array_equal(engine._clean(mask), mask)
        image = np.full((240, 320, 3), 130, np.uint8)
        image[50:190, 40:130] = (220, 210, 185)
        mask[:] = 0
        mask[50:190, 40:130] = 255
        self.assertGreater(engine.boundary_support(image, mask), .9)
        self.assertLess(engine.boundary_support(image, np.roll(mask, 150, axis=1)), .1)
        for med in (214, 215):
            np.testing.assert_array_equal(engine.wb(image, [med] * 3), image)
        with self.assertRaises(ValueError):
            engine.run('unused.jpg', F.ORIGINALS / 'sentinel')

    def test_spin_keeps_window_and_lid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'm.png'
            m = np.zeros((80, 120), np.uint8)
            m[10:70, 10:70] = 255
            m[20:30, 20:30] = 0
            m[15:55, 90:105] = 255
            Image.fromarray(m).save(path)
            np.testing.assert_array_equal(np.array(build_spin.mask_for(path, (120, 80))), m)

    def test_failed_promotion_restores_previous(self):
        with tempfile.TemporaryDirectory(dir=F.ROOT) as temp:
            root = Path(temp)
            out = root / 'delivery'
            stage = root / 'stage'
            out.mkdir()
            stage.mkdir()
            (out / 'sentinel').write_text('old')
            original_rename = Path.rename
            def fail_stage(path, destination):
                if path == stage:
                    raise OSError('injected failure')
                return original_rename(path, destination)
            with patch.object(F, 'previous_for', return_value=root / 'previous'), patch.object(Path, 'rename', fail_stage):
                with self.assertRaises(OSError):
                    F.promote(stage, out)
            self.assertEqual((out / 'sentinel').read_text(), 'old')


class WorkhorseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tools = self.root / 'site/tools'
        shutil.copytree(TOOLS, self.tools, ignore=shutil.ignore_patterns('__pycache__'))
        self.originals = self.root / 'PHOTOS/1-ORIGINALS/fixture'
        self.originals.mkdir(parents=True)
        self.meta = self.root / '_work/meta/fixture.json'
        self.meta.parent.mkdir(parents=True)
        self.source = self.originals / 'frame.jpg'
        photo = Image.new('RGB', (2300, 1700), (45, 85, 150))
        ImageDraw.Draw(photo).rectangle((320, 370, 1930, 1330), fill=(208, 201, 180))
        ImageDraw.Draw(photo).rectangle((600, 690, 1000, 955), fill=(185, 200, 215))
        photo.save(self.source, quality=96)
        self.mask = self.root / '_work/masks/fixture/frame.png'
        self.mask.parent.mkdir(parents=True)
        self.put_mask()
        self.spec = dict(slug='fixture', title='Fixture', brand_ok=None, photos=[
            dict(file='frame.jpg', role='hero', wide=False, alt='Cream box')])
        self.meta.write_text(json.dumps(self.spec))
        self.report = self.root / '_work/processed/report.json'
        self.final = self.root / 'PHOTOS/2-DONE/fixture'
        self.jpg = self.final / 'fixture-01-hero.jpg'

    def put_mask(self, rect=(320, 370, 1930, 1330)):
        m = Image.new('L', (2300, 1700))
        ImageDraw.Draw(m).rectangle(rect, fill=255)
        info = PngImagePlugin.PngInfo()
        info.add_text('source_sha256', F.digest(self.source))
        info.add_text('model', 'isnet-general-use')
        m.save(self.mask, pnginfo=info)

    def invoke(self, script='process_all', args=('fixture',), expected=0):
        r = subprocess.run([sys.executable, str(self.tools / (script + '.py')), *args],
                           capture_output=True, text=True, cwd=self.root)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return r.stdout

    def test_resume_queue_hashes_and_hold(self):
        original_hash = F.digest(self.source)
        self.invoke()
        for ext, (fmt, dims) in F.VARIANTS.items():
            with Image.open(self.final / ('fixture-01-hero' + ext)) as im:
                self.assertEqual((im.format, im.size), (fmt, dims))
                im.load()
                self.assertTrue(im.info.get('icc_profile'))
        side = json.loads((self.final / 'fixture.json').read_text())
        self.assertEqual(side['photos'][0]['source_file'], 'frame.jpg')
        with Image.open(self.jpg) as im:
            # Interior of the broad pale blue printed patch in the delivered square.
            pixel = im.getpixel((820, 1190))
            self.assertGreater(pixel[2] - pixel[0], 20)
        before = self.jpg.stat().st_mtime_ns, F.digest(self.jpg)
        self.assertIn('unchanged', self.invoke())
        shutil.copyfile(self.source, self.originals / 'new.jpg')
        self.assertIn('PENDING', self.invoke(expected=3))
        self.spec['photos'].append(dict(file='new.jpg', role=None))
        self.meta.write_text(json.dumps(self.spec))
        self.assertIn('EXTRA', self.invoke())
        (self.root / '_work/processed/fixture/frame.jpg').write_bytes(b'bad')
        self.assertIn('INCOMPLETE', self.invoke('finalize', expected=3))
        self.assertEqual(before, (self.jpg.stat().st_mtime_ns, F.digest(self.jpg)))
        (self.tools / 'overrides.json').write_text(json.dumps({'fixture/frame.jpg': {'skip': True}}))
        self.assertIn('No deliverable photos', self.invoke(expected=3))
        self.assertEqual(original_hash, F.digest(self.source))

    def test_collision_and_writer_lock(self):
        self.spec['photos'].append(dict(file='frame-wide.jpg', role='front'))
        self.meta.write_text(json.dumps(self.spec))
        self.assertIn('duplicate output', self.invoke(expected=3))
        self.assertFalse(self.final.exists())
        program = ("import sys, subprocess; sys.path.insert(0, 'site/tools'); import pipeline;"
                   "lock = pipeline.writer(); lock.__enter__(); "
                   "r = subprocess.run([sys.executable, 'site/tools/run_batch.py', 'fixture'], "
                   "capture_output=True, text=True); print(r.stderr); sys.exit(r.returncode)")
        r = subprocess.run([sys.executable, '-c', program], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Another local photo stage', r.stdout)

    def test_loose_intake_without_originals_folder(self):
        self.originals.rename(self.root / 'unfiled')
        self.originals.parent.rmdir()
        drop = self.root / 'PHOTOS/0-DROP'
        drop.mkdir()
        (drop / 'spin.mov').write_bytes(b'example')
        self.assertIn('PENDING', self.invoke(args=(), expected=3))
        queue = json.loads((self.root / '_work/pending.json').read_text())
        self.assertIn(str(Path('PHOTOS/0-DROP/spin.mov')), queue)

    def test_mask_provenance_and_focus(self):
        self.mask.write_bytes(b'invalid')
        self.assertIn('ERROR', self.invoke(expected=3))
        self.put_mask()
        self.spec['render_defaults'] = dict(focus_rect=[.30, .43, .40, .50], focus_min=5)
        self.meta.write_text(json.dumps(self.spec))
        self.assertIn('Printed focus reference failed', self.invoke(expected=3))
        self.assertFalse(self.jpg.exists())

    def test_wrong_mask_and_stable_hold_slots(self):
        self.put_mask((350, 40, 2050, 280))
        self.assertIn('AI outline has little support', self.invoke(expected=3))
        self.put_mask()
        # Earlier hero is held. Later take must keep slot 02 even if it is the only delivery.
        shutil.copyfile(self.source, self.originals / 'aaa.jpg')
        self.spec['photos'].insert(0, dict(file='aaa.jpg', role='hero'))
        self.meta.write_text(json.dumps(self.spec))
        (self.tools / 'overrides.json').write_text(json.dumps({'fixture/aaa.jpg': {'skip': True}}))
        self.invoke()
        side = json.loads((self.final / 'fixture.json').read_text())
        self.assertEqual([p['file'] for p in side['photos']], ['fixture-02-hero.jpg'])
        self.assertEqual(side['photos'][0]['source_file'], 'frame.jpg')

    def test_mask_producer_migrates_once(self):
        # Stub inference only. Exercise actual producer, PNG tags and resume path.
        self.mask.unlink()
        fake = self.tools / 'rembg.py'
        fake.write_text("from PIL import Image\n"
                        "def new_session(name): return object()\n"
                        "def remove(im, **kw):\n    mask = Image.new('L', im.size)\n    mask.paste(255, (100, 100, 800, 800))\n    return mask\n")
        self.invoke('make_masks')
        with Image.open(self.mask) as im:
            self.assertEqual(im.info['source_sha256'], F.digest(self.source))
            self.assertEqual(im.info['model'], 'isnet-general-use')
        fake.write_text("raise AssertionError('unexpected inference startup')\n")
        self.invoke('make_masks')

    def test_spin_sequence_and_failed_rebuild(self):
        frames = self.root / 'frames'
        masks = self.root / 'masks'
        frames.mkdir()
        masks.mkdir()
        for n in range(1, 11):
            im = Image.new('RGB', (180, 240), (40, 60, 90))
            ImageDraw.Draw(im).rectangle((36, 60, 144, 180), fill=(150 + n, 130, 110))
            im.save(frames / f'f_{n}.jpg')
            mask = Image.new('L', im.size)
            ImageDraw.Draw(mask).rectangle((36, 60, 144, 180), fill=255)
            mask.save(masks / f'f_{n}.png')
        args = ('fixture', str(frames), str(masks))
        self.invoke('build_spin', args)
        output = self.root / 'PHOTOS/3-SPIN/fixture'
        self.assertEqual(len(list((output / 'frames').glob('*.webp'))), 10)
        last = output / 'frames/009.webp'
        original_hash = F.digest(last)
        (masks / 'f_10.png').write_bytes(b'bad')
        self.invoke('build_spin', args, expected=1)
        self.assertEqual(original_hash, F.digest(last))
