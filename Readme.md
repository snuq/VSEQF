# VSE Quick Functions Addon For Blender

This script is designed to make Blender's VSE easier to use by implementing features often found in other video editors, or features that I find useful as a video editor.

## QuickFades
Enables one-click adding or changing a fade-in or fade-out.  Also enables one-click crossfading between multiple strips.

Can be found in the sequence editor properties panel, or by pressing the 'f' key over the sequencer.
Detected fades will also be shown on the active strip in the timeline, or in the edit strip properties panel.  Fades will be automatically moved if the edges of the strip are changed.
If context menus are enabled, fades can be set by right clicking on the edges of a strip.

The 'QuickFades' panel provides buttons for setting and removing fades.
* Fade Length

...The target length for fade editing or creating.
...This can be set to 0 to remove a fade.

* Set Fadein/Set Fadeout

...Allows easy adding and changing of fade in/out.  The script will check the curve for any fades already applied to the sequence (either manually or by the script), and edit them if found.
...These buttons can apply the same fade to multiple selected sequences at once.

* Clear Fades

...Remove fades on all selected strips.

* Transition Type

...Selects the type of transition for adding with the following buttons.

* Crossfade Prev/Next Sequence

...Allows easy adding of transitions between sequences.  This will simply find the closest sequence to the active sequence, and add a transition between them.

* Smart Cross to Prev/Next

...Adjust the length of the active sequence and the next sequence to create a transition of the target fade length.
...This will also attempt to avoid extending the sequences past their end points if possible.
