# VSE Quick Functions Addon For Blender

This script is designed to make Blender's VSE easier to use by implementing features often found in other video editors, or features that I find useful as a video editor.


## QuickFades
Enables one-click adding or changing a fade-in or fade-out.  
Also enables one-click crossfading between multiple strips.

Can be found in the sequence editor properties panel, or by pressing the 'f' key over the sequencer.  
Detected fades will also be shown on the active strip in the timeline, or in the edit strip properties panel.  Fades will be automatically moved if the edges of the strip are changed.
If context menus are enabled, fades can be set by right clicking on the edges of a strip.  

The 'QuickFades' panel provides buttons for setting and removing fades.

* __Fade Length__

   The target length for fade editing or creating.  
   This can be set to 0 to remove a fade.

* __Set Fadein/Set Fadeout__

   Allows easy adding and changing of fade in/out.  The script will check the curve for any fades already applied to the sequence (either manually or by the script), and edit them if found.  
   These buttons can apply the same fade to multiple selected sequences at once.

* __Clear Fades__

   Remove fades on all selected strips.

* __Transition Type__

   Selects the type of transition for adding with the following buttons.

* __Crossfade Prev/Next Sequence__

   Allows easy adding of transitions between sequences.  This will simply find the closest sequence to the active sequence, and add a transition between them.

* __Smart Cross to Prev/Next__

   Adjust the length of the active sequence and the next sequence to create a transition of the target fade length.  
   This will also attempt to avoid extending the sequences past their end points if possible.


## QuickSnaps
A menu for extra cursor and strip snapping functions.

Can be found in the sequence editor 'Strip' menu, or by pressing the 's' key over the sequencer.  
If context menu is enabled, some snaps will be found on right clicking the cursor, and some while right clicking strips.

* __Cursor To Nearest Second__

   Will round the cursor position to the nearest second, based on framerate.

* __Jump To Previous/Next Sequence__

   Snap the cursor to the previous or next sequence in the timeline.

* __Cursor To Beginning/End Of Active__

   Will move the cursor to the beginning or end of the active sequence.

* __Selected To Cursor__

   Snaps the beginning of selected strips to the cursor.  This is the same as the 'shift-s' shortcut in the VSE.

* __Selected Beginning/End To Cursor__

   Moves all selected sequences so their beginning/end is at the cursor.

* __Selected To Previous/Next Sequence__

   Detects the previous or next sequence in the timeline from the active sequence, and moves the active sequence so it's beginning or end matches the other sequence's end or beginning.


## QuickZooms
A menu with zoom shortcuts.

Can be found in the sequence editor 'View' menu, or by pressing the 'z' key over the sequencer.  
If context menus are enabled, can be found by right clicking in an open area.

* __Zoom All Strips__

   Zooms the sequencer out to show all sequences.

* __Zoom To Timeline__

   Zooms the sequencer to the timeline start and end.

* __Zoom Selected__

   Zooms the sequencer to show the currently selected sequence(s).

* __Zoom Cursor__

   Zooms the sequencer to an amount of frames around the cursor.

* __Size__

   How many frames should be shown by using Zoom Cursor. Changing this value will automatically activate Zoom Cursor.

* __Save Current Zoom__

   Saves the current zoom level and view position in the presets menu.

* __Zoom Presets__

   Submenu containing saved presets. Click the 'X' next to each preset to remove it, or click 'Clear All' to erase all presets.

* __Zoom (Time Lengths)__

   Several preset zoom values for convenience.


## QuickParents
This implements a parenting system for sequences, any children of a moved or cut sequence will have the same operations performed on them.  
If the sequence is cut, any children under the cursor will be cut as well, and the script will duplicate parent/child relationships to the cut sequences.  
If the parent sequence is resized and a child sequences have the same endpoints, they will be resized as well.


Can be found in the sequence editor properties panel under "Edit Strip", or by pressing the 'Ctrl-p' key over the sequencer.  
If context menus are enabled, the QuickParents popup menu will be shown when right clicking a sequence as well.  
Children or Parents of selected sequence will be shown in these places.

Parenting relationships are show in the timeline view for the active sequence, a light line indicates children of the active sequence, a dark line indicates a parent of the active sequence.

* __Select Children or Parent (Small Selection Button)__

   Selects any related sequences to the current sequence.  
   Also can be accomplished with the shortcut 'Shift-p'.

* __Clear Children or Parent (Small X Button)__

   Removes relationships from selected sequence.

* __Set Active As Parent__

   If multiple sequences are selected, this will set selected sequences as children of the active (last selected) sequence.

* __Cut/Move Sequence Children__

   Enables parenting operations on child sequences.

* __Auto-Select Children__

   When a parent sequence is selected, child sequences will be selected as well.

* __Auto-Delete Children__

   When a parent sequence is deleted, all children will be deleted as well.

These settings can also be found in the Quick Functions Settings menu.


## QuickList
Displays a list of loaded sequences and allows you to change various settings.

Can be found in the sequence editor properties panel on the QuickList tab.

* __Display__

   Changes the details that are displayed for each sequence:  

   * Settings

      Adds an extra area for editing the length, position, and proxy settings of each sequence.

   * Parenting

      Adds an extra area that displays children of each sequence.
   
   * Tags
   
      Adds an extra area that displays tags for each sequence.

* __Select/Deselect All Sequences__

   Like pressing the 'a' key in the sequencer, this will toggle the selection of all sequences.

* __Sort by__

   Reorders the list based on timeline position, title, or length.  
   Click the small arrow to change the sorting order.


Settings For Each Sequence:

* __Eye Icon__

   Mutes/unmutes sequence.

* __Padlock Icon__

   Locks/unlocks sequence.

* __Sequence Type Button__

   Allows selecting and deselecting the sequence.

* __Sequence Title__

   Allows editing of sequence name.

* __Len__

   See the sequence length in HH:MM:SS:FF format, and adjust the length.

* __Pos__

   See the sequence position in HH:MM:SS:FF, and adjust the position.

* __Proxy settings (Only visible when 'Settings' display is enabled)__

   Enable/disable proxy and sizes.  

* __Sub-Sequences (Only visible on meta sequences)__

   Displays sequences inside the meta sequence.

* __Tags (Only visible if 'Tags' display is enabled)__

   A list of tags for this sequence is shown.  
   Click the tag to select all sequences with this tag.
   Click the 'X' next to the tag to remove it from this sequence.

* __Children (Only visible if 'Parenting' display is enabled)__

   The child sequences will be displayed here.  
   Click the 'X' next to a child sequence to remove it from this sequence's children.

If a sequence is an effect, and it is applied to another sequence, it will be indented and placed below it's parent.

If QuickList is in Position sorting mode, up and down arrows will be displayed next to each strip, these can be used to swap position of a strip with the previous or next strip in the timeline.  If parenting is enabled, this will ignore child strips.  This may cause unpredictable behavior if strips are highly layered, it is best used on a very linear timeline.


## QuickProxy
Automatically sets proxies for imported strips, and optionally can generate them automatically as well.

All settings for QuickProxy are found in the Quick Functions Settings menu.

* __Enable Proxy On Import__

   Enables the given proxy settings on any compatible sequence type when it is imported.

* __Auto-Build Proxy On Import__

   Starts the proxy building process on imported sequences.  
   Will only function if Enable Proxy On Import is active.  
   This will cause a performance hit on Blender as it is generating the proxies in the background.

The other settings are standard proxy settings, see the Blender help documentation for information on them.


## QuickMarkers
Add markers to the timeline using name presets, or quickly jump to and remove any marker.  


Can be found in the sequence editor properties panel under 'QuickMarkers', also Alt-M in the sequencer.

* __New Preset__

   Enter a marker title into the text field, and click the + button to add a preset.

* __Place A Marker__

   Click on a marker button once a preset has been added to add a marker with this name at the current cursor location.  
   Adding a marker in the location of a previously existing marker will rename the marker to the marker preset name.

* __Remove A Preset__

   Click the X button next to a preset to remove it.

* __Deselect New Markers__

   With this enabled, newly created markers will be unselected to prevent accidental moving.

* __Marker List__

   Click a marker title to jump the cursor to this marker.  
   Click the X button next to a marker to delete it.


## QuickBatchRender
Render sequences in the timeline to individual files and automatically create a new copy of the current scene with these strips replaced with the rendered versions.  
Effects and unprocessed strips will still be in copied scene and unaffected.

Can be found in the sequence editor properties panel.

* __Batch Render__

   Begin the batch render process using the settings below.

* __Render Directory__

   Type in, or select the directory to render the files into.  
   If left blank, the default scene render directory will be used.

* __Render Only Selected__

   Only process selected strips, others will not be replaced.

* __Render Modifiers__

   Apply modifiers to rendered strips.  
   Uncheck this to copy the modifiers to the rendered strip instead.

* __Render Audio__

   Check this to process audio strips as separate strips.  
   Uncheck to not process audio strips.

* __Render Meta Strips__

   Drop-down menu to decide what is done with meta strips:

   * Ignore

      Meta strips will not be processed, only copied over.

   * Individual Substrips

      Process and replace all strips inside meta strips.  
      The rendered strips will remain grouped in a meta strip in the new scene.

   * Single Strip

      Process the entire meta strip as one strip, and replace it with a single rendered strip.

### Render Presets
Preset render settings for various types of strips.  Each type has a 'Scene Setting' option that will simply use the render settings of the current scene.

* __Opaque Strips__

   Strips with no transparency set.

* __Transparent Strips__

   Strips with transparency set.  
   Several render settings will not render any transparency information, be careful when selecting these!

* __Audio Strips__

   File type to use for rendering an audio strip.


