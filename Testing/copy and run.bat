cd ..
for %%I in (__init__.py, cuts.py, fades.py, grabs.py, markers.py, Readme.md, shortcuts.py, snaps.py, tags.py, threepoint.py, timeline.py, vseqf.py, zoom.py, vu_meter.py) do xcopy %%I "%UserProfile%\AppData\Roaming\Blender Foundation\Blender\4.0\scripts\addons\VSEQF-master" /y
"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
cmd /k
