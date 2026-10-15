"""minis_core/paths.py: where the art and minis.json are found for a checkout, a PyInstaller bundle, a py2app bundle and
a wheel install (pip install taskbar-fighters).  Pure: temp folders stand in for each layout."""
import os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402,F401  (puts the repo on sys.path)
from minis_core import atlas, paths  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


class Layouts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_checkout_uses_the_repo(self):
        self.assertTrue(paths.checkout())
        self.assertEqual(paths.bundle_root(), REPO)
        self.assertEqual(paths.assets_dir(), REPO / 'assets')
        self.assertEqual(paths.icon_path(), REPO / 'assets' / 'icon' / 'minis.ico')
        self.assertEqual(paths.settings_dir(), REPO)
        self.assertEqual(paths.qa_dir(), REPO / 'qa')
        self.assertEqual(atlas.ASSETS, REPO / 'assets')

    def test_pyinstaller_reads_meipass_and_settings_beside_the_exe(self):
        exe = self.tmp / 'TaskbarFighters' / 'TaskbarFighters.exe'
        with mock.patch.object(sys, 'frozen', True, create=True), mock.patch.object(sys, '_MEIPASS', str(self.tmp / '_internal'), create=True), \
                mock.patch.object(sys, 'executable', str(exe)):
            self.assertEqual(paths.bundle_root(), self.tmp / '_internal')
            self.assertEqual(paths.assets_hd_dir(), self.tmp / '_internal' / 'assets_hd')
            self.assertEqual(paths.settings_dir(), exe.resolve().parent)
            self.assertIsNone(paths.qa_dir())                            # never write inside a bundle

    def test_py2app_reads_resourcepath_and_settings_beside_the_app(self):
        app = self.tmp / 'Taskbar Fighters.app'
        exe = app / 'Contents' / 'MacOS' / 'Taskbar Fighters'
        with mock.patch.object(sys, 'frozen', True, create=True), mock.patch.dict(os.environ, {'RESOURCEPATH': str(app / 'Contents' / 'Resources')}), \
                mock.patch.object(sys, 'executable', str(exe)):
            if hasattr(sys, '_MEIPASS'):
                self.skipTest('running inside PyInstaller')
            self.assertEqual(paths.bundle_root(), app / 'Contents' / 'Resources')
            self.assertEqual(paths.settings_dir(), app.resolve().parent)

    def test_wheel_install_reads_the_asset_package_not_site_packages(self):
        site = self.tmp / 'site-packages'
        (site / 'minis_core').mkdir(parents=True)
        (site / 'minis.py').write_text('', encoding='utf-8')
        (site / 'assets' / 'icon').mkdir(parents=True)                   # someone else's top-level assets/: ignored
        pkg = site / paths.ASSET_PACKAGE
        (pkg / 'assets' / 'icon').mkdir(parents=True)
        with mock.patch.object(paths, 'REPO', site), mock.patch.object(paths, '_package_dir', lambda name: pkg):
            self.assertFalse(paths.checkout())
            self.assertEqual(paths.bundle_root(), pkg)
            self.assertEqual(paths.icon_path('minis-256.png'), pkg / 'assets' / 'icon' / 'minis-256.png')
            self.assertIsNone(paths.qa_dir())                            # never write into site-packages

    def test_the_package_without_art_falls_back_to_the_repo(self):
        empty = self.tmp / paths.ASSET_PACKAGE                             # the checkout's own package: only __init__.py
        empty.mkdir()
        with mock.patch.object(paths, 'checkout', lambda: False), mock.patch.object(paths, '_package_dir', lambda name: empty):
            self.assertEqual(paths.bundle_root(), paths.REPO)

    def test_the_wheel_maps_the_art_into_the_package(self):
        text = (REPO / 'pyproject.toml').read_text(encoding='utf-8')
        try:
            import tomllib
        except ImportError:                                                # pragma: no cover (3.11+ has it)
            self.skipTest('no tomllib')
        st = tomllib.loads(text)['tool']['setuptools']
        self.assertEqual(st['package-dir'], {f'{paths.ASSET_PACKAGE}.assets': 'assets', f'{paths.ASSET_PACKAGE}.assets_hd': 'assets_hd'})
        self.assertNotIn('assets', st['packages'])
        self.assertTrue((REPO / paths.ASSET_PACKAGE / '__init__.py').is_file())


if __name__ == '__main__':
    unittest.main()
