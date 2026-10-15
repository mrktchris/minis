"""Taskbar Fighters' art, as installed by the wheel: assets/ (64 px sheets, effects, the icon) and assets_hd/ (128 px).

In a git checkout this package holds only this file: the art stays at the repository root (assets/, assets_hd/), and
pyproject.toml maps those two folders into this package when it builds the wheel, so `pip install taskbar-fighters`
never puts generic top-level folders named assets/ into site-packages.  minis_core/paths.py finds the art either way.
"""
