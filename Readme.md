# VSE Quick Functions Addon For Blender

This script is designed to make Blender's VSE easier to use by implementing features often found in other video editors, or features that I find useful as a video editor.



## Sequence Editor Additions
The built-in 'grab', 'select', 'cut', 'delete', 'make meta strip' and 'import' operators have been added to, this enables:

* Sequence Parenting

   Child sequences will follow parents.
   Child edges that match the parent's edge will move along with the parent.

* Ripple Editing

   While in grab mode, press the alt key to toggle between ripple, ripple-pop, and normal mode.  
   Ripple mode will move all sequences after the grabbed sequence the same amount.
   Ripple-Pop will allow you to move a sequence above and out of a line, automatically closing the gap left behind.  This will only operate when one sequence is grabbed.

* Edge Grab Improvements

   When an edge is moved into another sequence, the selected sequence will be moved up a channel to allow the edge to be moved.

* Marker Moving Improvements

   Markers can be grabbed by right-click dragging the marker line as well as the bottom marker indicator.

* Right-Click Context Menus

   Right-click and hold to open a popup menu allowing different operations to be performed depending on what is clicked on.  
   See the QuickContext section for more information.

* Making Meta Strip Additions

   If Cut/Move Children is on, child sequences will be added to a meta strip when a parent is added.  
   Effect sequences with a single input will be automatically added to meta strips when their input sequence is added.

* Cut Sequence Additions

   Child sequences of a parent will be automatically cut as well as the parent.  
   Ripple cuts enabled, press Alt-K to trim and slide one side of the selected sequences.  
   Effect strips are now duplicated to both sides of a cut strip, this includes an entire effect stack.  
   Crossfades and other two-input effect strips are handled properly now. If the effect is applied to the right side of a cut, it will be applied correctly. (See https://developer.blender.org/T50877 )  
   The active strip after a cut is correctly handled now, if the mouse is on the right side of a cut, the right sequence will be active as well as selected.

* Delete Sequence Additions

   Deleting a sequence can also delete child sequences if enabled.  
   Ripple delete enabled, press Alt-X or Alt-Delete to delete the sequence, and move all following sequences back to fill the gap.

* Import Additions

   Allows automatic proxy settings to be applied to Movie and Image types while being imported.  
   Allows proxies to be automatically generated when importing a Movie or Image.  
   Allows setting the length of a single imported image in frames.  
   When a movie sequence with sound is imported, the sound may be automatically parented to the video.  
   Provides additional options for placing an imported sequence on the timeline:  

   * Import At Frame

      Standard import behavior, places new sequences at the current frame.

   * Insert At Frame

      Following sequence will be moved forward by the length of the imported sequence.

   * Cut And Insert At Frame

      All sequences at the current frame will be cut and all following sequences will be moved forward by the length of the imported sequence.

   * Import At End

      Places the imported sequences at the end of the timeline.



## QuickContext
Enables right-click and hold in the sequencer to pop up a context menu allowing for different operations depending on what is clicked on.

'Enable Context Menu' must be checked in the Quick Functions Settings menu.

None of the menu options are unique, some are built-in in blender, some are provided by other parts of this script.

Note that all menus start with the undo operator.

The different menu types are:

* __Sequences__

   Click on the center of a sequence to show a menu providing some settings for the active sequence, and selected sequences.  

* __Sequence Left/Right Handles__

   Click on or near the edge of a sequence to pop up a menu allowing for the changing and clearing of the fade in or out.

* __Cursor__

   Click on or near the cursor to show a menu providing some snapping options.

* __Markers__

   Click on or near a marker to show a menu providing some marker operations.

* __Empty Area__

   Click in an empty area of the sequencer to show a menu providing options to add sequences, and to zoom the sequencer.



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

#### Render Presets
Preset render settings for various types of strips.  Each type has a 'Scene Setting' option that will simply use the render settings of the current scene.

* __Opaque Strips__

   Strips with no transparency set.

* __Transparent Strips__

   Strips with transparency set.  
   Several render settings will not render any transparency information, be careful when selecting these!

* __Audio Strips__

   File type to use for rendering an audio strip.



## QuickTags
Create tags, text snippets that can describe sequences, and apply them to any sequences in the timeline.  All sequences with a specific tag can be easily selected with one click.

* __All Tags__

   This list shows all tags on all sequences in the timeline.  
   Click a tag to select all sequences with that tag.  
   Click the '+' button to add that tag to all selected sequences.

* __New Tag__

   Type a tag into the field, and press the '+' button to add to all selected strips.  This tag will now show up in the list above as well.

* __Show All Selected__

   This button toggles the lower list between showing the tags for the active sequence (Active Tags) or showing tags for all selected sequences (Selected Tags).

* __Active Tags__

   Shows a list of tags for the active sequence.
   Click a tag to select all sequences with this tag.
   Click the 'X' button to remove the tag from the active sequence.

* __Selected Tags__

   Shows a list of tags for all selected sequence.
   Click a tag to select all sequences with this tag.
   Click the 'X' button to remove the tag from all selected sequences.

* __Clear Selected Tags__

   Removes all tags from all selected sequences.



## QuickCuts
Provides a quick interface for basic and advanced cutting and trimming functions.

* __Cut All Sequences__

   If enabled, all sequences under the cursor (besides locked sequences) will be affected by any button in this panel.  
   If disabled, only selected sequences will be affected.

* __Frames To Insert__

   When the 'Cut Insert' function is used, the number of frames here will be inserted.

* __Cut__

   Basic soft cut function, equivalent to the 'K' shortcut in the VSE.

* __Cut Insert__

   Performs a soft cut, then slides all sequences following the cut down the timeline by the amount of frames defined in the 'Frames To Insert' variable.

* __UnCut Left/UnCut Right__

   Merges a selected sequence with the one to the left or right if they are from the same source file, and have not been slid on the timeline.  
   Useful for 'undoing' an accidental cut.

* __Delete__

   Removes selected sequences from the timeline.

* __Ripple Delete__

   Removes selected sequences from the timeline, and attempts to remove any empty space left behind.

* __Trim Left/Right__

   Removes any part of the selected sequences to the left or right of the cursor.

* __Slide Trim Left/Right__

   Removes any part of the selected sequences to the left of the cursor, then slides the remaining sequence back or forward to where the original edge was.

* __Ripple Trim Left/Right__

   Trims one side of the selected sequences, then slides the sequence, and all following sequences back to attempt to fill the empty space

* __Timeline To All__

   Sets the start and end points of the VSE timeline to fit all sequences loaded in.

* __Timeline To Selected__

   Sets the start and end points of the VSE timeline to fit the currently selected sequences. 

* __Start To All/End To All__

   Sets only the start or end of the VSE timeline to fit all sequences.

* __Start To Selected/End To Selected__

   Sets only the start or end of the VSE timeline to fit the selected sequences.

* __Full Timeline Setup__

   Moves all sequences back so they start on frame 1, then sets the start and endpoints of the timeline so they encompass all sequences.



