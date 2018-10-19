# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

"""
2.8 update notes: https://wiki.blender.org/wiki/User:NBurn/2.80_Python_API_Changes
   scene_update_post handler has been removed, need a new way to run the continous function, or hope it is added back?
   any time variable types are set (ie, variable = Class()), the ':' is used now (variable: Class())
   bgl is gone? how to draw overlays now?

Known Issues:
   shift-s not working properly with multiple clip edges selected
   Sometimes undo pushing breaks... not sure what's going on there
   Uncut does not work on movieclip type sequences... there appears to be no way of getting the sequence's source file.
   Right now the script cannot apply a vertical zoom level, as far as I can tell this is missing functionality in
       Blenders python api.

Future Possibilities:
   way to drag over an area of a strip and have it cut out or ripple-cut out
   special tags with time index and length, displayed in overlay as clip markers
   Ripple insert... need to think about how to do this, but I want it!
   Copy/paste wrapper that copies strip animation data

Changelog:
0.93
   Added seconds offset and seconds position display to edit panel
   Added 'compact' edit strip panel, displays more information in a smaller space than the original.
   Added categories to panels
   Implemented new function wrappers, many features should now be more reliable, and new small features are added
      New 'Grab' operator - parenting and ripple features are reliable now, press 'Alt' to toggle ripple mode
      New 'Select' operator - can now right-click-drag multiple files
      New 'Cut' operator - parenting and ripple is now properly handled
      New 'Delete' operator - can ripple delete, and can remove children, New ripple delete shortcut - Alt-Delete and Alt-X
      New 'Meta Make' operator - automatically adds child strips to new metastrip
      New strip importer operator - has some new features and will auto-parent and auto-generate proxies
   Replaced the sequencer Strip and Add menus so they can use the custom operators, also new option to simplify strip menu by removing some items
   New ripple cut shortcuts - Alt-K will ripple trim the strip based on which side the mouse is on
   Minimized continuous function handler, only needs to detect new strips and renames now
   Implemented graphic display of fades and parent/child relationships of the active strip
   Cursor following is back, works properly at all zoom levels now!
   Implemented Quick3Point - a basic 3point editing workflow, import from the file browser to the clip editor, then to the sequencer.
   Auto-Set Timeline Operator - move strips up to frame 1, set timeline start to frame 1, set timeline end to last frame of last strip
   The new cut operator now fixes effect sequence chains - it will duplicate single input effects (such as speed control) to the newly cut sequence, and it will fix crossfades that should be applied to the right cut sequence.  See https://developer.blender.org/T50877 for more info on the bug.
   Now can save and recall zoom levels in the vse.  No way to do vertical (channel) zooms yet tho...
   Right-click context menu option added, hold right click to activate it.  Options will differ depending on what is clicked on - cursor, sequence, sequence handles, markers, empty area

0.94 (In progress)
   Frame skipping now works with reverse playback as well, and fixed poor behavior.
   Added QuickShortcuts - timeline and sequence movement using the numpad.  Thanks to tintwotin for the ideas!
   Added option to snap cursor to a dragged edge (if only one is grabbed)
   Many improvements to Quick3Point interface

Todo before release:
    update readme: add QuickShortcuts, snap to grabbed edge
"""


import bpy
import bgl
import blf
import math
import time
import os
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ImportHelper


bl_info = {
    "name": "VSE Quick Functions",
    "description": "Improves functionality of the sequencer by adding new menus and functions for snapping, adding fades, zooming, sequence parenting, ripple editing, playback speed, and more.",
    "author": "Hudson Barkley (Snu/snuq/Aritodo)",
    "version": (0, 9, 3),
    "blender": (2, 79, 0),
    "location": "Sequencer Panels; Sequencer Menus; Sequencer S, F, Z, Ctrl-P, Shift-P, Alt-M, Alt-K Shortcuts",
    "wiki_url": "https://github.com/snuq/VSEQF",
    "tracker_url": "https://github.com/snuq/VSEQF/issues",
    "category": "Sequencer"
}
vseqf_draw_handler = None

right_click_time = 0.5


#Miscellaneous Functions
def vseqf_parenting():
    prefs = get_prefs()
    if prefs.parenting and bpy.context.scene.vseqf.children:
        return True
    else:
        return False


def vseqf_proxy():
    prefs = get_prefs()
    if prefs.proxy and bpy.context.scene.vseqf.enable_proxy:
        return True
    else:
        return False


def get_vse_position(context):
    region = context.region
    view = region.view2d

    #determine the view area
    width = region.width
    height = region.height
    left, bottom = view.region_to_view(0, 0)
    right, top = view.region_to_view(width, height)
    return [left, right, bottom, top]


def redraw_sequencers():
    for area in bpy.context.screen.areas:
        if area.type == 'SEQUENCE_EDITOR':
            area.tag_redraw()


def effect_children(sequence, to_check):
    effects = []
    for seq in to_check:
        if hasattr(seq, 'input_1'):
            if seq.input_1 == sequence:
                effects.append(seq)
        if hasattr(seq, 'input_2'):
            if seq.input_2 == sequence:
                effects.append(seq)
    return effects


def fix_effect(effect, apply_from, apply_to, to_check):
    #do whatever is needed to 'fix' the given effect and make it apply to the new strip
    sub_effects = effect_children(effect, to_check)
    if not hasattr(effect, 'input_2'):
        #just a one-input effect, just copy it to the new sequence and check its children
        new_effect = copy_effect(effect, apply_to)
        for sub_effect in sub_effects:
            fix_effect(sub_effect, effect, new_effect, to_check)
    else:
        #this effect has 2 inputs, need to check if it needs to be reassigned to work properly now
        if effect.input_1 == apply_from and effect.frame_final_start == apply_from.frame_final_end:
            effect.input_1 = apply_to
        elif effect.input_2 == apply_from and effect.frame_final_start == apply_from.frame_final_end:
            effect.input_2 = apply_to
        else:
            return
        #have to do this extra stuff to get the sequencer to realize the effect positions need to be reset
        original_channel = effect.channel
        effect.channel = effect.channel + 1
        effect.channel = original_channel


def copy_effect(effect, copy_to):
    #copies a given single-input effect to the given sequence
    old_selects = []
    sequences = current_sequences(bpy.context)
    for sequence in sequences:
        if sequence.select:
            old_selects.append(sequence)
            sequence.select = False
    effect.select = True
    bpy.ops.sequencer.duplicate()
    new_effect = current_selected(bpy.context)[0]
    copy_to.select = True
    bpy.context.scene.sequence_editor.active_strip = new_effect
    bpy.ops.sequencer.reassign_inputs()
    new_effect.channel = effect.channel
    new_effect.select = False
    effect.select = False
    copy_to.select = False
    for sequence in old_selects:
        sequence.select = True
    return new_effect


def fix_effects(cut_pairs, sequences):
    effects = []
    for sequence in sequences:
        if hasattr(sequence, 'input_1'):
            effects.append(sequence)
    for cut_pair in cut_pairs:
        left, right = cut_pair
        if left and right:
            left_effects = effect_children(left, effects)
            for effect in left_effects:
                fix_effect(effect, left, right, effects)


def inside_meta_strip():
    try:
        if len(bpy.context.scene.sequence_editor.meta_stack) > 0:
            return True
    except:
        pass
    return False


def apply_proxy_settings(seq):
    vseqf = bpy.context.scene.vseqf
    seq_type = seq.rna_type.name
    if seq_type in ['Movie Sequence', 'Image Sequence', 'MovieClip']:
        seq.use_proxy = True
        seq.proxy.build_25 = vseqf.proxy_25
        seq.proxy.build_50 = vseqf.proxy_50
        seq.proxy.build_75 = vseqf.proxy_75
        seq.proxy.build_100 = vseqf.proxy_100
        seq.proxy.quality = vseqf.proxy_quality
        return True
    return False


def find_sequences_end(sequences):
    end = 1
    for sequence in sequences:
        if sequence.frame_final_end > end:
            end = sequence.frame_final_end
    return end


def find_sequences_start(sequences):
    if not sequences:
        return 1
    start = sequences[0].frame_final_start
    for sequence in sequences:
        if sequence.frame_final_start < start:
            start = sequence.frame_final_start
    return start


def current_active(context):
    try:
        active_strip = context.scene.sequence_editor.active_strip
    except:
        return None
    if active_strip:
        return active_strip
    else:
        return None


def current_selected(context):
    selected = context.selected_sequences
    if selected:
        return selected
    else:
        return []


def current_sequences(context):
    sequences = context.sequences
    if sequences:
        return sequences
    else:
        return []


def get_prefs():
    if __name__ in bpy.context.user_preferences.addons:
        prefs = bpy.context.user_preferences.addons[__name__].preferences
    else:
        prefs = VSEQFTempSettings()
    return prefs


def draw_line(sx, sy, ex, ey, width, color=(1.0, 1.0, 1.0, 1.0)):
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glColor4f(*color)
    bgl.glLineWidth(width)
    bgl.glBegin(bgl.GL_LINE_STRIP)
    bgl.glVertex2i(sx, sy)
    bgl.glVertex2i(ex, ey)
    bgl.glEnd()


def draw_rect(x, y, w, h, color=(1.0, 1.0, 1.0, 1.0)):
    bgl.glBegin(bgl.GL_QUADS)
    bgl.glColor4f(*color)
    bgl.glVertex2f(x, y)
    bgl.glVertex2f(x+w, y)
    bgl.glVertex2f(x+w, y+h)
    bgl.glVertex2f(x, y+h)
    bgl.glEnd()


def draw_ngon(verts, color=(1.0, 1.0, 1.0, 1.0)):
    while len(verts) < 4:
        verts.append(verts[-1])
    bgl.glBegin(bgl.GL_QUADS)
    bgl.glColor4f(*color)
    for vert in verts:
        bgl.glVertex2f(*vert)
    bgl.glEnd()


def draw_text(x, y, size, text, color=(1.0, 1.0, 1.0, 1.0)):
    font_id = 0
    bgl.glColor4f(*color)
    blf.position(font_id, x, y, 0)
    blf.size(font_id, size, 72)
    blf.draw(font_id, text)


def find_crossfade(sequences, first_sequence, second_sequence):
    for sequence in sequences:
        if hasattr(sequence, 'input_1') and hasattr(sequence, 'input_2'):
            if (sequence.input_1 == first_sequence and sequence.input_2 == second_sequence) or (sequence.input_2 == first_sequence and sequence.input_1 == second_sequence):
                return sequence
    return False


def sequencer_area_filled(left, right, bottom, top, omit, sequences=False, quick=True):
    """Iterates through sequences and checks if any are partially or fully in the given area
    Arguments:
        left: Starting frame of the area to check
        right: Ending frame of the area to check
        bottom: Lowest channel of the area to check
        top: Highest channel of the area to check, set to -1 for infinite range
        omit: List of sequences to ignore
        sequences: List of sequences to check, if not given, bpy.context.scene.sequence_editor.sequences will be used
        quick: If True, the function will stop iterating and return True on the first match, otherwise returns list of 
            all matches

    Returns: If quick=True, returns True if a sequence is in the area, False if none are in the area.  
        If quick==False, returns a list of all matching sequences if any are in the given area."""

    if top != -1:
        if bottom > top:
            old_top = top
            top = bottom
            bottom = old_top
    matches = []
    if not sequences:
        sequences = current_sequences(bpy.context)
    for sequence in sequences:
        if sequence not in omit:
            if sequence.channel >= bottom and (sequence.channel <= top or top == -1):
                start = sequence.frame_final_start
                end = sequence.frame_final_end
                if (start > left and start < right) or (end > left and end < right) or (start < left and end > right):
                    if quick:
                        return True
                    else:
                        matches.append(sequence)
    if matches and not quick:
        return matches
    return False


def under_cursor(sequence, frame):
    """Check if a sequence is visible on a frame
    Arguments:
        sequence: VSE sequence object to check
        frame: Integer, the frame number

    Returns: True or False"""
    if sequence.frame_final_start < frame and sequence.frame_final_end > frame:
        return True
    else:
        return False


def edit_panel(self, context):
    """Used to add extra information and variables to the VSE 'Edit Strip' panel"""

    #load up preferences
    if __name__ in context.user_preferences.addons:
        prefs = context.user_preferences.addons[__name__].preferences
    else:
        prefs = VSEQFTempSettings()

    scene = context.scene
    active_sequence = current_active(context)
    if not active_sequence:
        return
    vseqf = scene.vseqf
    layout = self.layout
    row = layout.row()
    row.label("Final Offset: "+timecode_from_frames(active_sequence.frame_offset_start, scene.render.fps)+" : "+timecode_from_frames(active_sequence.frame_offset_end, scene.render.fps))
    row = layout.row()
    row.label("Final Start: "+timecode_from_frames(active_sequence.frame_final_start, scene.render.fps))

    if prefs.fades:
        #display info about the fade in and out of the current sequence
        fadein = fades(sequence=active_sequence, mode='detect', direction='in')
        fadeout = fades(sequence=active_sequence, mode='detect', direction='out')

        row = layout.row()
        if fadein > 0:
            row.label("Fadein: "+str(round(fadein))+" Frames")
        else:
            row.label("No Fadein Detected")
        if fadeout > 0:
            row.label("Fadeout: "+str(round(fadeout))+" Frames")
        else:
            row.label("No Fadeout Detected")

    if prefs.parenting:
        #display info about parenting relationships
        selected = context.selected_sequences
        sequences = current_sequences(context)

        children = find_children(active_sequence, sequences=sequences)
        parent = find_parent(active_sequence)

        box = layout.box()
        #List relationships for active sequence
        if parent:
            row = box.row()
            split = row.split(percentage=.8, align=True)
            split.label("Parent: "+parent.name)
            split.operator('vseqf.quickparents', text='', icon="BORDER_RECT").action = 'select_parent'
            split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_parent'
        if len(children) > 0:
            row = box.row()
            split = row.split(percentage=.8, align=True)
            subsplit = split.split(percentage=.1)
            subsplit.prop(scene.vseqf, 'expanded_children', icon="TRIA_DOWN" if scene.vseqf.expanded_children else "TRIA_RIGHT", icon_only=True, emboss=False)
            subsplit.label("Children: "+children[0].name)
            split.operator('vseqf.quickparents', text='', icon="BORDER_RECT").action = 'select_children'
            split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_children'
            if scene.vseqf.expanded_children:
                index = 1
                while index < len(children):
                    row = box.row()
                    split = row.split(percentage=.1)
                    split.label()
                    split.label(children[index].name)
                    index = index + 1

        row = box.row()
        split = row.split()
        if len(selected) <= 1:
            split.enabled = False
        split.operator('vseqf.quickparents', text='Set Active As Parent').action = 'add'
        row.prop(vseqf, 'children', toggle=True)
        row = box.row()
        row.prop(vseqf, 'select_children', toggle=True)
        row.prop(vseqf, 'delete_children', toggle=True)


def draw_quicksettings_menu(self, context):
    """Draws the general settings menu for QuickContinuous related functions"""

    del context
    layout = self.layout
    layout.menu('vseqf.settings_menu', text="Quick Functions Settings")


def sequences_after_frame(sequences, frame, add_locked=True, add_parented=True, add_effect=True):
    """Finds sequences after a given frame
    Arguments:
        sequences: List containing the VSE Sequence objects that will be searched
        frame: Integer, the frame to check for sequences following
        add_locked: Boolean, if false, locked sequences will be ignored
        add_parented: Boolean, if false, sequences with a set parent will be ignored
        add_effect: Boolean, if false, sequences of the effect type will be ignored

    Returns: A list of VSE Sequence objects"""
    update_sequences = []
    for seq in sequences:
        if seq.frame_final_start >= frame:
            #sequence starts after frame
            if (not seq.lock) or add_locked:
                #always adding locked, or sequence is not locked
                if add_parented or (not find_parent(seq)):
                    #always adding parents, or parent not found
                    if add_effect or (not hasattr(seq, 'input_1')):
                        update_sequences.append(seq)
    return update_sequences


def sequences_between_frames(sequences, start_frame, end_frame, add_locked=True, add_parented=True, add_effect=True):
    """Finds sequences that are visible between two given frames
    Arguments:
        sequences: List containing the VSE Sequence objects that will be searched
        start_frame: Integer, beginning frame number to search at
        end_frame: Integer, ending frame to search at
        add_locked: Boolean, if false, locked sequences will be ignored
        add_parented: Boolean, if false, sequences with a set parent will be ignored
        add_effect: Boolean, if false, sequences of the effect type will be ignored

    Returns: A list of VSE Sequence objects"""
    update_sequences = []
    for seq in sequences:
        if seq.frame_final_start >= start_frame and seq.frame_final_end <= end_frame:
            if (not seq.lock) or add_locked:
                #always adding locked, or sequence is not locked
                if add_parented or (not find_parent(seq)):
                    #always adding parents, or parent not found
                    if add_effect or (not hasattr(seq, 'input_1')):
                        update_sequences.append(seq)
    return update_sequences


def find_close_sequence(sequences, selected_sequence, direction, mode='overlap', sounds=False, effects=True, children=True):
    """Finds the closest sequence in one direction to the given sequence
    Arguments:
        sequences: List of sequences to search through
        selected_sequence: VSE Sequence object that will be used as the basis for the search
        direction: String, must be 'next' or 'previous', determines the direction to search in
        mode: String, determines how the sequences are searched
            'overlap': Only returns sequences that overlap selected_sequence
            'channel': Only returns sequences that are in the same channel as selected_sequence
            'simple': Just looks for the previous or next frame_final_start
            <any other string>: All sequences are returned
        sounds: Boolean, if False, 'SOUND' sequence types are ignored
        effects: Boolean, if False, effect strips that are applied to another strip are ignored
        children: Boolean, if False, strips that are children of another will be ignored

    Returns: VSE Sequence object, or Boolean False if no matching sequence is found
    :rtype: bpy.types.Sequence"""

    overlap_nexts = []
    overlap_previous = []
    nexts = []
    previous = []
    found = None

    if mode == 'simple':
        nexts = []
        previous = []
        for current_sequence in sequences:
            #don't bother with sound or effect type sequences
            if (current_sequence.type != 'SOUND') or sounds:
                #check if the sequence is a child of another, ignore if needed
                if not children:
                    if find_parent(current_sequence):
                        continue
                #check if the sequence is an effect of the selected sequence, ignore if so
                if hasattr(current_sequence, 'input_1'):
                    if current_sequence.input_1 == selected_sequence or not effects:
                        continue
                if current_sequence.frame_final_start <= selected_sequence.frame_final_start and current_sequence != selected_sequence:
                    previous.append(current_sequence)
                elif current_sequence.frame_final_start >= selected_sequence.frame_final_start and current_sequence != selected_sequence:
                    nexts.append(current_sequence)
        if direction == 'next':
            if len(nexts) > 0:
                found = min(nexts, key=lambda seq: (seq.frame_final_start - selected_sequence.frame_final_start))
        else:
            if len(previous) > 0:
                found = min(previous, key=lambda seq: (selected_sequence.frame_final_start - seq.frame_final_start))
    else:
        #iterate through sequences to find all sequences to one side of the selected sequence
        for current_sequence in sequences:
            #don't bother with sound or effect type sequences
            if (current_sequence.type != 'SOUND') or sounds:
                #check if the sequence is a child of another, ignore if needed
                if not children:
                    if find_parent(current_sequence):
                        continue
                #check if the sequence is an effect of the selected sequence, ignore if so
                if hasattr(current_sequence, 'input_1'):
                    if current_sequence.input_1 == selected_sequence or not effects:
                        continue
                if current_sequence.frame_final_start >= selected_sequence.frame_final_end:
                    #current sequence is after selected sequence
                    if not (mode == 'channel' and selected_sequence.channel != current_sequence.channel):
                        #dont append if channel mode and sequences are not on same channel
                        nexts.append(current_sequence)
                elif current_sequence.frame_final_end <= selected_sequence.frame_final_start:
                    #current sequence is before selected sequence
                    if not (mode == 'channel' and selected_sequence.channel != current_sequence.channel):
                        #dont append if channel mode and sequences are not on same channel
                        previous.append(current_sequence)
                if (current_sequence.frame_final_start > selected_sequence.frame_final_start) & (current_sequence.frame_final_start < selected_sequence.frame_final_end) & (current_sequence.frame_final_end > selected_sequence.frame_final_end):
                    #current sequence startpoint is overlapping selected sequence
                    overlap_nexts.append(current_sequence)
                if (current_sequence.frame_final_end > selected_sequence.frame_final_start) & (current_sequence.frame_final_end < selected_sequence.frame_final_end) & (current_sequence.frame_final_start < selected_sequence.frame_final_start):
                    #current sequence endpoint is overlapping selected sequence
                    overlap_previous.append(current_sequence)

        nexts_all = nexts + overlap_nexts
        previous_all = previous + overlap_previous
        if direction == 'next':
            if mode == 'overlap':
                if len(overlap_nexts) > 0:
                    found = min(overlap_nexts, key=lambda overlap: abs(overlap.channel - selected_sequence.channel))
            elif mode == 'channel':
                if len(nexts) > 0:
                    found = min(nexts, key=lambda next_seq: (next_seq.frame_final_start - selected_sequence.frame_final_end))
            else:
                if len(nexts_all) > 0:
                    found = min(nexts_all, key=lambda next_seq: (next_seq.frame_final_start - selected_sequence.frame_final_end))
        else:
            if mode == 'overlap':
                if len(overlap_previous) > 0:
                    found = min(overlap_previous, key=lambda overlap: abs(overlap.channel - selected_sequence.channel))
            elif mode == 'channel':
                if len(previous) > 0:
                    found = min(previous, key=lambda prev: (selected_sequence.frame_final_start - prev.frame_final_end))
            else:
                if len(previous_all) > 0:
                    found = min(previous_all, key=lambda prev: (selected_sequence.frame_final_start - prev.frame_final_end))
    return found


def timecode_from_frames(frame, fps, levels=0, subsecond_type='miliseconds'):
    """Converts a frame number to a standard timecode in the format: HH:MM:SS:FF
    Arguments:
        frame: Integer, frame number to convert to a timecode
        fps: Integer, number of frames per second if using 'frames' subsecond type
        levels: Integer, limits the number of timecode elements:
            1: returns: FF
            2: returns: SS:FF
            3: returns: MM:SS:FF
            4: returns: HH:MM:SS:FF
            0: returns an auto-cropped timecode with no zero elements
        subsecond_type: String, determines the format of the final element of the timecode:
            'miliseconds': subseconds will be divided by 100
            'frames': subseconds will be divvided by the current fps

    Returns: A string timecode"""

    #ensure the levels value is sane
    if levels > 4:
        levels = 4

    #set the sub second divisor type
    if subsecond_type == 'frames':
        subsecond_divisor = fps
    else:
        subsecond_divisor = 100

    #check for negative values
    if frame < 0:
        negative = True
        frame = abs(frame)
    else:
        negative = False

    #calculate divisions, starting at largest and taking the remainder of each to calculate the next smaller
    total_hours = math.modf(float(frame)/fps/60.0/60.0)
    total_minutes = math.modf(total_hours[0] * 60)
    remaining_seconds = math.modf(total_minutes[0] * 60)
    hours = int(total_hours[1])
    minutes = int(total_minutes[1])
    seconds = int(remaining_seconds[1])
    subseconds = int(round(remaining_seconds[0] * subsecond_divisor))

    hours_text = str(hours).zfill(2)
    minutes_text = str(minutes).zfill(2)
    seconds_text = str(seconds).zfill(2)
    subseconds_text = str(subseconds).zfill(2)

    #format and return the time value
    time_text = subseconds_text
    if levels > 1 or (levels == 0 and seconds > 0):
        time_text = seconds_text+'.'+time_text
    if levels > 2 or (levels == 0 and minutes > 0):
        time_text = minutes_text+':'+time_text
    if levels > 3 or (levels == 0 and hours > 0):
        time_text = hours_text+':'+time_text
    if negative:
        time_text = '-'+time_text
    return time_text


def copy_curves(copy_from, copy_to, scene_from, scene_to):
    """Copies animation curves from one sequence to another, this is needed since the copy operator doesn't do this...
    Arguments:
        copy_from: VSE Sequence object to copy from
        copy_to: VSE Sequence object to copy to
        scene_from: scene that copy_from is in
        scene_to: scene that copy_to is in"""
    if hasattr(scene_from.animation_data, 'action'):
        scene_to.animation_data_create()
        scene_to.animation_data.action = bpy.data.actions.new(name=scene_to.name+'Action')
        for fcurve in scene_from.animation_data.action.fcurves:
            path = fcurve.data_path
            path_start = path.split('[', 1)[0]
            path_end = path.split(']')[-1]
            test_path = path_start+'["'+copy_from.name+'"]'+path_end
            if path == test_path:
                new_path = path_start+'["'+copy_to.name+'"]'+path_end
                new_curve = scene_to.animation_data.action.fcurves.new(data_path=new_path)
                new_curve.extrapolation = fcurve.extrapolation
                new_curve.mute = fcurve.mute
                #copy keyframe points to new_curve
                for keyframe in fcurve.keyframe_points:
                    new_curve.keyframe_points.add()
                    new_keyframe = new_curve.keyframe_points[-1]
                    new_keyframe.type = keyframe.type
                    new_keyframe.amplitude = keyframe.amplitude
                    new_keyframe.back = keyframe.back
                    new_keyframe.co = keyframe.co
                    new_keyframe.easing = keyframe.easing
                    new_keyframe.handle_left = keyframe.handle_left
                    new_keyframe.handle_left_type = keyframe.handle_left_type
                    new_keyframe.handle_right = keyframe.handle_right
                    new_keyframe.handle_right_type = keyframe.handle_right_type
                    new_keyframe.interpolation = keyframe.interpolation
                    new_keyframe.period = keyframe.period
                new_curve.update()


class VSEQFCompactEdit(bpy.types.Panel):
    """Panel for displaying QuickList"""
    bl_label = "Edit Strip Compact"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for active sequence
        if not current_active(context):
            return False
        else:
            return prefs.edit

    def draw(self, context):
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        scene = context.scene
        strip = current_active(context)
        vseqf = scene.vseqf
        layout = self.layout
        fps = scene.render.fps / scene.render.fps_base

        row = layout.row()
        split = row.split(percentage=.8)
        split.prop(strip, 'name', text="")
        split.label("("+strip.type+")")

        if strip.type == 'SOUND':
            row = layout.row(align=True)
            sub = row.row(align=True)
            sub.active = not strip.mute
            sub.prop(strip, 'volume', text='Volume')
            row.prop(strip, "mute", toggle=True, icon_only=True)
            row.prop(strip, "lock", toggle=True, icon_only=True)
            row = layout.row()
            row.prop(strip, "pan")
            row.prop(strip, "pitch")
        else:
            row = layout.row(align=True)
            sub = row.row(align=True)
            sub.active = not strip.mute
            split = sub.split(percentage=.3, align=True)
            split.prop(strip, "blend_type", text="")
            split.prop(strip, "blend_alpha", text="Opacity", slider=True)
            row.prop(strip, "mute", toggle=True, icon_only=True)
            row.prop(strip, "lock", toggle=True, icon_only=True)
            row = layout.row(align=True)
            row.prop(strip, "color_saturation", text="Saturation")
            row.prop(strip, "color_multiply", text="Multiply")

        col = layout.column()
        sub = col.column()
        sub.enabled = not strip.lock
        row = sub.row(align=True)
        row.prop(strip, "channel")
        row.prop(strip, "frame_start", text="Position: ("+timecode_from_frames(strip.frame_final_start, fps)+")")
        row = sub.row()
        row.prop(strip, "frame_final_duration", text="Length: ("+timecode_from_frames(strip.frame_final_duration, fps)+")")
        row = sub.row(align=True)
        row.prop(strip, "frame_offset_start", text="In Offset: ("+timecode_from_frames(strip.frame_offset_start, fps)+")")
        row.prop(strip, "frame_offset_end", text="Out Offset: ("+timecode_from_frames(strip.frame_offset_end, fps)+")")

        if prefs.fades:
            #display info about the fade in and out of the current sequence
            fadein = fades(sequence=strip, mode='detect', direction='in')
            fadeout = fades(sequence=strip, mode='detect', direction='out')

            row = layout.row()
            if fadein > 0:
                row.label("Fadein: "+str(round(fadein))+" Frames")
            else:
                row.label("No Fadein Detected")
            if fadeout > 0:
                row.label("Fadeout: "+str(round(fadeout))+" Frames")
            else:
                row.label("No Fadeout Detected")

        if prefs.parenting:
            #display info about parenting relationships
            sequence = current_active(context)
            selected = context.selected_sequences
            if len(scene.sequence_editor.meta_stack) > 0:
                #inside a meta strip
                sequencer = scene.sequence_editor.meta_stack[-1]
            else:
                #not inside a meta strip
                sequencer = scene.sequence_editor
            if hasattr(sequencer, 'sequences'):
                sequences = sequencer.sequences
            else:
                sequences = []

            children = find_children(sequence, sequences=sequences)
            parent = find_parent(sequence)

            box = layout.box()
            #List relationships for active sequence
            if parent:
                row = box.row()
                split = row.split(percentage=.8, align=True)
                split.label("Parent: "+parent.name)
                split.operator('vseqf.quickparents', text='', icon="BORDER_RECT").action = 'select_parent'
                split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_parent'
            if len(children) > 0:
                row = box.row()
                split = row.split(percentage=.8, align=True)
                subsplit = split.split(percentage=.1)
                subsplit.prop(vseqf, 'expanded_children', icon="TRIA_DOWN" if scene.vseqf.expanded_children else "TRIA_RIGHT", icon_only=True, emboss=False)
                subsplit.label("Children: "+children[0].name)
                split.operator('vseqf.quickparents', text='', icon="BORDER_RECT").action = 'select_children'
                split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_children'
                if vseqf.expanded_children:
                    index = 1
                    while index < len(children):
                        row = box.row()
                        split = row.split(percentage=.1)
                        split.label()
                        split.label(children[index].name)
                        index = index + 1

            row = box.row()
            split = row.split()
            split.operator('vseqf.quickparents', text='Set Active As Parent').action = 'add'
            if len(selected) <= 1:
                split.enabled = False
            row.prop(vseqf, 'children', toggle=True)
            row = box.row()
            row.prop(vseqf, 'select_children', toggle=True)
            row.prop(vseqf, 'delete_children', toggle=True)


#Functions related to continuous update
@persistent
def vseqf_continuous(scene):
    if not bpy.context.screen or bpy.context.screen.scene != scene:
        return
    vseqf = scene.vseqf
    if vseqf.last_frame != scene.frame_current:
        #scene frame was changed, assume nothing else happened
        pass
        #vseqf.last_frame = scene.frame_current
    else:
        #something in the scene was changed by the user, figure out what
        try:
            sequencer = scene.sequence_editor
            sequences = sequencer.sequences
        except:
            return
        new_sequences = []
        new_end = scene.frame_current
        build_proxies = False
        for sequence in sequences:
            if sequence.new:
                if not (sequence.type == 'META' or hasattr(sequence, 'input_1')):
                    new_sequences.append(sequence)
                sequence.last_name = sequence.name
                sequence.new = False
            if sequence.last_name != sequence.name:
                #sequence was renamed or duplicated, update parenting if the original doesnt still exist
                if sequence.name and sequence.last_name:
                    original = False
                    for seq in sequences:
                        if seq.name == sequence.last_name:
                            #this sequence was just duplicated or copied, dont do anything
                            original = seq
                            break
                    if not original:
                        #sequence was renamed, update parenting
                        children = find_children(sequence.last_name, name=True, sequences=sequences)
                        for child in children:
                            child.parent = sequence.name
                sequence.last_name = sequence.name
        if new_sequences:
            for sequence in new_sequences:
                if sequence.type not in ['ADJUSTMENT', 'TEXT', 'COLOR', 'MULTICAM'] and sequence.frame_final_end > new_end:
                    new_end = sequence.frame_final_end
                if vseqf_parenting() and vseqf.autoparent:
                    #autoparent
                    if sequence.type == 'SOUND':
                        for seq in new_sequences:
                            if seq.type == 'MOVIE':
                                if seq.filepath == sequence.sound.filepath:
                                    sequence.parent = seq.name
                                    break
                if vseqf_proxy():
                    #enable proxies on sequence
                    applied_proxies = apply_proxy_settings(sequence)
                    if applied_proxies and vseqf.build_proxy:
                        build_proxies = True
            if build_proxies:
                #Build proxies if needed
                last_selected = bpy.context.selected_sequences
                for seq in sequences:
                    if seq in new_sequences:
                        seq.select = True
                    else:
                        seq.select = False
                area = False
                region = False
                for screenarea in bpy.context.window.screen.areas:
                    if screenarea.type == 'SEQUENCE_EDITOR':
                        area = screenarea
                        for arearegion in area.regions:
                            if arearegion.type == 'WINDOW':
                                region = arearegion
                if area and region:
                    override = bpy.context.copy()
                    override['area'] = area
                    override['region'] = region
                    bpy.ops.sequencer.rebuild_proxy(override, 'INVOKE_DEFAULT')
                for seq in sequences:
                    if seq in last_selected:
                        seq.select = True
                    else:
                        seq.select = False
            if vseqf.snap_new_end:
                scene.frame_current = new_end


def vseqf_draw():
    prefs = get_prefs()
    active_strip = current_active(bpy.context)
    if not active_strip:
        return
    region = bpy.context.region
    view = region.view2d

    #determine pixels per frame and channel
    width = region.width
    height = region.height
    left, bottom = view.region_to_view(0, 0)
    right, top = view.region_to_view(width, height)
    shown_width = right - left
    shown_height = top - bottom
    channel_px = height / shown_height
    frame_px = width / shown_width

    length = active_strip.frame_final_duration
    active_x = active_strip.frame_final_start + (length / 2)
    active_y = active_strip.channel + 0.5
    active_left, active_top = view.view_to_region(active_strip.frame_final_start, active_strip.channel+1)
    active_right, active_top2 = view.view_to_region(active_strip.frame_final_end, active_strip.channel+1)
    active_pos_x, active_pos_y = view.view_to_region(active_x, active_strip.channel + 0.5)
    if active_top == 12000:
        active_top = active_top2
    active_width = length * frame_px
    if active_top != 12000:
        fade_height = channel_px / 20
        text_size = 10
        #display fades
        if prefs.fades and active_width > text_size * 6:
            if active_left != 12000:
                if active_pos_x == 12000:
                    active_pos_x = int(active_left + (active_width / 2))
                fadein = int(fades(sequence=active_strip, mode='detect', direction='in'))
                if fadein and length:
                    fadein_percent = fadein / length
                    draw_rect(active_left, active_top - (fade_height * 2), fadein_percent * active_width, fade_height, color=(.5, .5, 1, .75))
                    draw_text(active_left, active_top, text_size, 'In: '+str(fadein))
            if active_right != 12000:
                if active_pos_x == 12000:
                    active_pos_x = int(active_right - (active_width / 2))
                fadeout = int(fades(sequence=active_strip, mode='detect', direction='out'))
                if fadeout and length:
                    fadeout_percent = fadeout / length
                    fadeout_width = active_width * fadeout_percent
                    draw_rect(active_right - fadeout_width, active_top - (fade_height * 2), fadeout_width, fade_height, color=(.5, .5, 1, .75))
                    draw_text(active_right - (text_size * 4), active_top, text_size, 'Out: '+str(fadeout))
        if prefs.parenting and active_pos_x != 12000:
            if active_pos_y == 12000:
                active_pos_y = int(active_top - (channel_px / 2))
            children = find_children(active_strip)
            parent = find_parent(active_strip)
            if parent:
                parent_x = parent.frame_final_start + (parent.frame_final_duration / 2)
                parent_y = parent.channel + 0.5
                distance_x = parent_x - active_x
                distance_y = parent_y - active_y
                pixel_x_distance = int(distance_x * frame_px)
                pixel_y_distance = int(distance_y * channel_px)
                pixel_x = active_pos_x + pixel_x_distance
                pixel_y = active_pos_y + pixel_y_distance
                draw_line(active_pos_x, active_pos_y, pixel_x, pixel_y, 2, color=(0.0, 0.0, 0.0, 0.2))
            for child in children:
                child_x = child.frame_final_start + (child.frame_final_duration / 2)
                child_y = child.channel + 0.5
                distance_x = child_x - active_x
                distance_y = child_y - active_y
                pixel_x_distance = int(distance_x * frame_px)
                pixel_y_distance = int(distance_y * channel_px)
                pixel_x = active_pos_x + pixel_x_distance
                pixel_y = active_pos_y + pixel_y_distance
                draw_line(active_pos_x, active_pos_y, pixel_x, pixel_y, 2, color=(1.0, 1.0, 1.0, 0.2))


#Functions and classes related to QuickShortcuts
def nudge_selected(frame=0, channel=0):
    """Moves the selected sequences by a given amount, ignoring parenting."""

    for sequence in bpy.context.selected_sequences:
        oldframe = sequence.frame_start
        if frame:
            if sequence.select_left_handle or sequence.select_right_handle:
                if sequence.select_left_handle:
                    sequence.frame_final_start = sequence.frame_final_start + frame
                if sequence.select_right_handle:
                    sequence.frame_final_end = sequence.frame_final_end + frame
            else:
                newframe = sequence.frame_start + frame
                sequence.frame_start = newframe
                oldframe = newframe
        if channel:
            newchannel = sequence.channel + channel
            if newchannel > 0:
                sequence.channel = newchannel
                sequence.frame_start = oldframe


def find_marker(frame, direction):
    """Attempts to find a marker in the given direction.
    'direction' must be 'next' or 'previous'.
    returns a marker object, or None if none found.
    """

    return_marker = None
    best_delta = None
    for marker in bpy.context.scene.timeline_markers:
        if direction == 'next':
            if marker.frame > frame:
                delta = marker.frame - frame
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    return_marker = marker
        else:
            if marker.frame < frame:
                delta = frame - marker.frame
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    return_marker = marker
    return return_marker


def find_edge(frame, direction):
    """Attemts to find the closest sequence edge in the given direction.
    'direction' must be 'next' or 'previous'.
    returns a frame number, or None if none found.
    """

    new_frame = None
    best_delta = None
    for sequence in bpy.context.scene.sequence_editor.sequences:
        edges = [sequence.frame_final_start, sequence.frame_final_end]
        for edge in edges:
            if direction == 'next':
                if edge > frame:
                    delta = edge - frame
                    if best_delta is None or delta < best_delta:
                        best_delta = delta
                        new_frame = edge
            else:
                if edge < frame:
                    delta = frame - edge
                    if best_delta is None or delta < best_delta:
                        best_delta = delta
                        new_frame = edge
    return new_frame


class VSEQFQuickShortcutsNudge(bpy.types.Operator):
    bl_idname = 'vseqf.nudge_selected'
    bl_label = 'Move the selected sequences'

    direction = bpy.props.EnumProperty(name='Direction', items=[("UP", "Up", "", 1), ("DOWN", "Down", "", 2), ("LEFT", "Left", "", 3), ("RIGHT", "Right", "", 4), ("LEFT-M", "Left Medium", "", 5), ("RIGHT-M", "Right Medium", "", 6), ("LEFT-L", "Left Large", "", 7), ("RIGHT-L", "Right Large", "", 8)])

    def execute(self, context):
        bpy.ops.ed.undo_push()
        render = context.scene.render
        second = int(round(render.fps / render.fps_base))
        if self.direction == 'UP':
            nudge_selected(channel=1)
        elif self.direction == 'DOWN':
            nudge_selected(channel=-1)
        elif self.direction == 'LEFT':
            nudge_selected(frame=-1)
        elif self.direction == 'LEFT-M':
            nudge_selected(frame=0 - int(round(second/2)))
        elif self.direction == 'LEFT-L':
            nudge_selected(frame=0 - second)
        elif self.direction == 'RIGHT':
            nudge_selected(frame=1)
        elif self.direction == 'RIGHT-M':
            nudge_selected(frame=int(round(second/2)))
        elif self.direction == 'RIGHT-L':
            nudge_selected(frame=second)
        return{'FINISHED'}


class VSEQFQuickShortcutsSpeed(bpy.types.Operator):
    bl_idname = 'vseqf.change_speed'
    bl_label = 'Raise or lower playback speed'

    speed_change = bpy.props.EnumProperty(name='Type', items=[("UP", "Up", "", 1), ("DOWN", "Down", "", 2)])

    def execute(self, context):
        if self.speed_change == 'UP':
            if not context.screen.is_animation_playing:
                bpy.ops.screen.animation_play()
                context.scene.vseqf.step = 1
            elif context.scene.vseqf.step == 0:
                bpy.ops.screen.animation_play()
            elif context.scene.vseqf.step < 7:
                context.scene.vseqf.step = context.scene.vseqf.step + 1
        elif self.speed_change == 'DOWN':
            if not context.screen.is_animation_playing:
                bpy.ops.screen.animation_play(reverse=True)
                context.scene.vseqf.step = -1
            elif context.scene.vseqf.step == 0:
                bpy.ops.screen.animation_play()
            elif context.scene.vseqf.step > -7:
                context.scene.vseqf.step = context.scene.vseqf.step - 1
        if context.screen.is_animation_playing and context.scene.vseqf.step == 0:
            bpy.ops.screen.animation_play()
        return{'FINISHED'}


class VSEQFQuickShortcutsSkip(bpy.types.Operator):
    bl_idname = 'vseqf.skip_timeline'
    bl_label = 'Skip timeline location'

    type = bpy.props.EnumProperty(name='Type', items=[("NEXTSECOND", "One Second Forward", "", 1), ("LASTSECOND", "One Second Backward", "", 2), ("NEXTEDGE", "Next Clip Edge", "", 3), ("LASTEDGE", "Last Clip Edge", "", 4), ("LASTMARKER", "Last Marker", "", 5), ("NEXTMARKER", "Next Marker", "", 6)])

    def execute(self, context):
        bpy.ops.ed.undo_push()
        second_frames = int(round(context.scene.render.fps / context.scene.render.fps_base))
        if self.type == "NEXTSECOND":
            context.scene.frame_current = context.scene.frame_current + second_frames
        elif self.type == "LASTSECOND":
            context.scene.frame_current = context.scene.frame_current - second_frames
        elif self.type == "NEXTEDGE":
            edge = find_edge(context.scene.frame_current, direction='next')
            if edge is not None:
                context.scene.frame_current = edge
        elif self.type == "LASTEDGE":
            edge = find_edge(context.scene.frame_current, direction='previous')
            if edge is not None:
                context.scene.frame_current = edge
        elif self.type == "LASTMARKER":
            marker = find_marker(context.scene.frame_current, direction='previous')
            if marker:
                context.scene.frame_current = marker.frame
        elif self.type == "NEXTMARKER":
            marker = find_marker(context.scene.frame_current, direction='next')
            if marker:
                context.scene.frame_current = marker.frame
        return{'FINISHED'}


class VSEQFQuickShortcutsResetPlay(bpy.types.Operator):
    bl_idname = 'vseqf.reset_playback'
    bl_label = 'Reset playback to normal speed and play'

    direction = bpy.props.EnumProperty(name='Direction', items=[("FORWARD", "Forward", "", 1), ("BACKWARD", "Backward", "", 2)])

    def execute(self, context):
        if self.direction == 'BACKWARD':
            context.scene.vseqf.step = 0
            bpy.ops.screen.animation_play(reverse=True)
        else:
            context.scene.vseqf.step = 0
            bpy.ops.screen.animation_play()
        return{'FINISHED'}


#Functions and classes related to threepoint editing
def update_clip_import(self, context):
    #todo: prevent values from being extended past sequence bounds
    fps = round(context.scene.render.fps / context.scene.render.fps_base)
    if self.import_frames_in >= fps:
        self.import_frames_in = 0
        self.import_seconds_in = self.import_seconds_in + 1
    if self.import_seconds_in >= 60:
        self.import_seconds_in = 0
        self.import_minutes_in = self.import_minutes_in + 1
    self.import_frame_in = (self.import_minutes_in * 60 * fps) + (self.import_seconds_in * fps) + self.import_frames_in
    if self.import_frames_length >= fps:
        self.import_frames_length = 0
        self.import_seconds_length = self.import_seconds_length + 1
    if self.import_seconds_length >= 60:
        self.import_seconds_length = 0
        self.import_minutes_length = self.import_minutes_length + 1
    self.import_frame_length = (self.import_minutes_length * 60 * fps) + (self.import_seconds_length * fps) + self.import_frames_length


def three_point_draw_callback(self, context):
    colorfg = (1.0, 1.0, 1.0, 1.0)
    colorbg = (0.1, 0.1, 0.1, 1.0)
    colormg = (0.5, 0.5, 0.5, 1.0)

    scale = self.scale
    half_scale = scale / 2.0
    quarter_scale = scale / 4.0
    double_scale = scale * 2
    width = context.region.width
    height = context.region.height

    #draw in/out bars
    draw_rect(0, height - double_scale, width, double_scale, colorbg)
    draw_rect(0, height - half_scale - 2, width, 4, colormg)
    draw_rect(0, height - scale - half_scale - 2, width, 4, colormg)
    draw_rect(0, height - scale - 1, width, 2, colormg)

    #draw in/out icons
    in_x = self.in_percent * width
    draw_rect(in_x, height - scale, quarter_scale, scale, colorfg)
    draw_ngon([(in_x, height - half_scale), (in_x + half_scale, height), (in_x + half_scale, height - scale)], colorfg)
    if self.in_percent <= .5:
        in_text_x = in_x + scale
    else:
        in_text_x = 0 + half_scale
    draw_text(in_text_x, height - scale + 2, scale - 2, "In: "+str(self.in_frame), colorfg)

    out_x = self.out_percent * width
    draw_rect(out_x - quarter_scale, height - double_scale, quarter_scale, scale, colorfg)
    draw_ngon([(out_x, height - half_scale - scale), (out_x - half_scale, height - scale), (out_x - half_scale, height - double_scale)], colorfg)
    if self.out_percent >= .5:
        out_text_x = 0 + half_scale
    else:
        out_text_x = out_x + half_scale
    draw_text(out_text_x, height - double_scale + 2, scale - 2, "Length: "+str(self.out_frame - self.in_frame), colorfg)


class VSEQFThreePointBrowserPanel(bpy.types.Panel):
    bl_label = "3Point Edit"
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOLS'
    bl_category = "Quick 3Point"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
        if not prefs.threepoint:
            return False
        params = context.space_data.params
        selected_file = params.filename
        if selected_file:
            filename, extension = os.path.splitext(selected_file)
            if extension.lower() in bpy.path.extensions_movie:
                full_filename = os.path.join(params.directory, params.filename)
                if os.path.exists(full_filename):
                    return True
        return False

    def draw(self, context):
        del context
        layout = self.layout
        row = layout.row()
        row.operator('vseqf.threepoint_import_to_clip', text='Import To Clip Editor')


class VSEQFThreePointImportToClip(bpy.types.Operator):
    bl_idname = "vseqf.threepoint_import_to_clip"
    bl_label = "Import Movie To Clip Editor"

    def execute(self, context):
        params = context.space_data.params
        filename = os.path.join(params.directory, params.filename)
        clip = bpy.data.movieclips.load(filename, check_existing=True)
        proxy = vseqf_proxy()
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for space in area.spaces:
                    if space.type == 'CLIP_EDITOR':
                        space.clip = clip
                        override = context.copy()
                        override['area'] = area
                        override['space_data'] = space
                        if context.scene.vseqf.build_proxy:
                            bpy.ops.clip.rebuild_proxy(override)

        if proxy:
            apply_proxy_settings(clip)
        return {'FINISHED'}


class VSEQFThreePointPanel(bpy.types.Panel):
    bl_label = "3 Point Edit"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
        if not prefs.threepoint:
            return False
        if context.space_data.clip:
            return True
        else:
            return False

    def draw(self, context):
        layout = self.layout
        clip = context.space_data.clip

        row = layout.row()
        row.operator('vseqf.threepoint_modal_operator', text='Set In/Out')
        fps = context.scene.render.fps / context.scene.render.fps_base
        row = layout.row()
        if clip.import_settings.import_frame_in != -1:
            row.label("In: "+str(clip.import_settings.import_frame_in)+' ('+timecode_from_frames(clip.import_settings.import_frame_in, fps)+')')
        else:
            row.label("In: Not Set")
        row = layout.row()
        col = row.column(align=True)
        col.prop(clip.import_settings, 'import_minutes_in', text='Minutes In')
        col.prop(clip.import_settings, 'import_seconds_in', text='Seconds In')
        col.prop(clip.import_settings, 'import_frames_in', text='Frames In')
        row = layout.row()
        col = row.column(align=True)
        col.prop(clip.import_settings, 'import_minutes_length', text='Minutes Length')
        col.prop(clip.import_settings, 'import_seconds_length', text='Seconds Length')
        col.prop(clip.import_settings, 'import_frames_length', text='Frames Length')
        row = layout.row()
        if clip.import_settings.import_frame_length != -1:
            row.label("Length: "+str(clip.import_settings.import_frame_length)+' ('+timecode_from_frames(clip.import_settings.import_frame_length, fps)+')')
        else:
            row.label("Length Not Set")
        row = layout.row()
        row.operator('vseqf.threepoint_import', text='Import At Cursor').type = 'cursor'
        row = layout.row()
        row.operator('vseqf.threepoint_import', text='Replace Active Sequence').type = 'replace'
        row = layout.row()
        row.operator('vseqf.threepoint_import', text='Insert At Cursor').type = 'insert'
        row = layout.row()
        row.operator('vseqf.threepoint_import', text='Cut Insert At Cursor').type = 'cut_insert'
        row = layout.row()
        row.operator('vseqf.threepoint_import', text='Import At End').type = 'end'


class VSEQFThreePointImport(bpy.types.Operator):
    bl_idname = "vseqf.threepoint_import"
    bl_label = "Imports a movie clip into the VSE as a movie sequence"

    type = bpy.props.StringProperty()

    def execute(self, context):
        override_area = False
        for area in context.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                if not override_area:
                    override_area = area
                if area.spaces[0].view_type != 'PREVIEW':
                    override_area = area
        override = context.copy()
        if override_area:
            override['area'] = override_area
            active_strip = current_active(context)
            sequencer = context.scene.sequence_editor
            if not sequencer:
                context.scene.sequence_editor_create()
            sequences = context.scene.sequence_editor.sequences_all
            for seq in sequences:
                seq.select = False
                seq.select_left_handle = False
                seq.select_right_handle = False
            clip = context.space_data.clip
            filepath = bpy.path.abspath(clip.filepath)
            frame_start = find_sequences_start(sequences) - clip.frame_duration - 1
            bpy.ops.sequencer.movie_strip_add(override, filepath=filepath, frame_start=frame_start, replace_sel=True, use_framerate=False)
            sound_sequence = False
            movie_sequence = False
            sequences = context.scene.sequence_editor.sequences_all
            for seq in sequences:
                if seq.select:
                    if seq.type == 'MOVIE':
                        movie_sequence = seq
                    if seq.type == 'SOUND':
                        sound_sequence = seq
            if not movie_sequence:
                return {'CANCELLED'}
            if clip.import_settings.import_frame_in == -1:
                frame_in = 0
            else:
                frame_in = clip.import_settings.import_frame_in
            if clip.import_settings.import_frame_length == -1:
                frame_length = clip.frame_duration
            else:
                frame_length = clip.import_settings.import_frame_length
            import_pos = context.scene.frame_current
            offset = clip.import_settings.import_frame_length
            if self.type == 'replace':
                if not active_strip:
                    return {'CANCELLED'}
                if sound_sequence:
                    sound_sequence.channel = active_strip.channel + 1
                movie_sequence.channel = active_strip.channel
                frame_start = active_strip.frame_final_start - frame_in
                move_forward = offset - active_strip.frame_final_duration
                children = find_children(active_strip)
                if active_strip.type == 'MOVIE':
                    original_filepath = active_strip.filepath
                else:
                    original_filepath = None
                if move_forward > 0:
                    move_frame = active_strip.frame_final_start
                else:
                    move_frame = active_strip.frame_final_end
                bpy.ops.sequencer.select_all(override, action='DESELECT')
                active_strip.select = True
                for child in children:
                    if child.type == 'SOUND' and child.sound.filepath == original_filepath and child.frame_final_start == active_strip.frame_final_start and child.frame_start == active_strip.frame_start and child.frame_final_end == active_strip.frame_final_end:
                        child.select = True
                        children.remove(child)
                        break
                bpy.ops.sequencer.delete(override)
                if move_forward != 0:
                    bpy.ops.vseqf.cut(use_frame=True, frame=move_frame, type='INSERT_ONLY', use_insert=True, insert=move_forward, use_all=True, all=True)
                for child in children:
                    child.parent = movie_sequence.name
            elif self.type == 'end':
                import_pos = find_sequences_end(sequences)
                frame_start = import_pos - frame_in
            elif self.type == 'insert':
                bpy.ops.vseqf.cut(type='INSERT_ONLY', use_insert=True, insert=offset, use_all=True, all=True)
                frame_start = import_pos - frame_in
            elif self.type == 'cut_insert':
                bpy.ops.vseqf.cut(type='INSERT', use_insert=True, insert=offset, use_all=True, all=True)
                frame_start = import_pos - frame_in
            else:
                frame_start = import_pos - frame_in
            context.scene.sequence_editor.active_strip = movie_sequence
            movie_sequence.frame_offset_start = frame_in  #crashing blender in replace mode???
            movie_sequence.frame_final_duration = frame_length
            movie_sequence.frame_start = frame_start
            bpy.ops.sequencer.select_all(override, action='DESELECT')
            movie_sequence.select = True
            if sound_sequence:
                sound_sequence.select = True
                channel = sound_sequence.channel
                sound_sequence.frame_offset_start = frame_in
                #sound_sequence.frame_offset_end = frame_length
                sound_sequence.channel = channel
                sound_sequence.frame_start = frame_start
                sound_sequence.frame_final_end = movie_sequence.frame_final_end
                if context.scene.vseqf.autoparent:
                    sound_sequence.parent = movie_sequence.name

            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class VSEQFThreePointOperator(bpy.types.Operator):
    """Controls the 3point editing functionality in the Clip Editor"""
    bl_idname = "vseqf.threepoint_modal_operator"
    bl_label = "Controls the 3point editing functionality in the Clip Editor"

    _handle = None
    scale = 20
    mouse_down = False
    mouse_x = 0
    mouse_y = 0
    editing_in = False
    editing_length = False
    in_percent = 0
    out_percent = 1
    clip = None
    in_frame = 1
    out_frame = 2
    start_frame = 0
    original_scene = None
    last_in = -1
    last_length = -1

    def update_import_values(self, context):
        fps = round(context.scene.render.fps / context.scene.render.fps_base)
        settings = self.clip.import_settings
        remainder, frames_in = divmod(settings.import_frame_in, fps)
        minutes_in, seconds_in = divmod(remainder, 60)
        remainder, frames_length = divmod(settings.import_frame_length, fps)
        minutes_length, seconds_length = divmod(remainder, 60)
        settings.import_frames_in = frames_in
        settings.import_seconds_in = seconds_in
        settings.import_minutes_in = minutes_in
        settings.import_frames_length = frames_length
        settings.import_seconds_length = seconds_length
        settings.import_minutes_length = minutes_length

    def update_pos(self, context, mouse_x, mouse_y):
        self.mouse_x = mouse_x
        self.mouse_y = mouse_y
        clip = self.clip
        clip_length = clip.frame_duration

        percent = mouse_x / context.region.width
        if percent < 0:
            percent = 0
        if percent > 1:
            percent = 1
        if self.editing_in:
            if percent > self.out_percent:
                percent = self.out_percent
            self.in_percent = percent
            self.in_frame = int(round(clip_length * self.in_percent))
            if self.in_frame >= self.out_frame:
                self.in_frame = self.out_frame - 1
            context.scene.frame_current = self.in_frame + 1
            clip.import_settings.import_frame_in = self.in_frame
            clip.import_settings.import_frame_length = self.out_frame - self.in_frame
            context.scene.frame_start = self.in_frame
        elif self.editing_length:
            if percent < self.in_percent:
                percent = self.in_percent
            self.out_percent = percent
            self.out_frame = int(round(clip_length * self.out_percent))
            if self.out_frame <= self.in_frame:
                self.out_frame = self.in_frame + 1
            context.scene.frame_current = self.out_frame - 1
            clip.import_settings.import_frame_length = self.out_frame - self.in_frame
            context.scene.frame_end = self.out_frame

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type == 'SPACE' and event.value == 'PRESS':
            #play/pause
            bpy.ops.screen.animation_play()
        if event.type == 'MOUSEMOVE':
            if self.mouse_down:
                self.update_pos(context, event.mouse_region_x, event.mouse_region_y)
                self.update_import_values(context)

        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                self.mouse_down = True
                height = context.region.height
                width = context.region.width
                if event.mouse_region_x > 0 and event.mouse_region_x < width:
                    if event.mouse_region_y < height and event.mouse_region_y > height - self.scale:
                        self.editing_in = True
                        self.update_pos(context, event.mouse_region_x, event.mouse_region_y)
                    elif event.mouse_region_y < height - self.scale and event.mouse_region_y > height - (self.scale * 2):
                        self.editing_length = True
                        self.update_pos(context, event.mouse_region_x, event.mouse_region_y)
                    else:
                        self.finish_modal(context)
                        return {'FINISHED'}
                else:
                    self.finish_modal(context)
                    return {'FINISHED'}
            elif event.value == 'RELEASE':
                self.mouse_down = False
                self.editing_in = False
                self.editing_length = False

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.clip.import_settings.import_frame_in = self.last_in
            self.clip.import_settings.import_frame_length = self.last_length
            self.finish_modal(context)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def finish_modal(self, context):
        bpy.types.SpaceClipEditor.draw_handler_remove(self._handle, 'WINDOW')
        bpy.ops.scene.delete()
        context.screen.scene = self.original_scene
        self.update_import_values(context)
        #context.scene.frame_current = self.start_frame

    def invoke(self, context, event):
        del event
        space = context.space_data
        if space.type == 'CLIP_EDITOR':
            self.start_frame = context.scene.frame_current
            self.clip = context.space_data.clip
            self.last_in = self.clip.import_settings.import_frame_in
            self.last_length = self.clip.import_settings.import_frame_length
            if self.clip.import_settings.import_frame_in == -1:
                self.in_frame = 0
                self.clip.import_settings.import_frame_in = 0
                self.in_percent = 0
            else:
                self.in_frame = self.clip.import_settings.import_frame_in
                if self.clip.frame_duration > self.in_frame:
                    self.in_percent = self.in_frame / self.clip.frame_duration
                else:
                    self.in_percent = 0
            if self.clip.import_settings.import_frame_length == -1:
                self.out_frame = self.clip.frame_duration
                self.clip.import_settings.import_frame_length = self.out_frame - self.in_frame
            else:
                self.out_frame = self.clip.import_settings.import_frame_length + self.in_frame
                if self.clip.frame_duration >= self.out_frame:
                    self.out_percent = self.out_frame / self.clip.frame_duration
            self.update_import_values(context)
            self.original_scene = context.scene
            bpy.ops.scene.new(type='EMPTY')
            context.scene.name = 'ThreePoint Temp'
            context.scene.frame_current = 1
            clip = context.space_data.clip
            filepath = bpy.path.abspath(clip.filepath)
            context.scene.sequence_editor_create()
            context.scene.sequence_editor.sequences.new_movie(name='ThreePoint Temp', filepath=filepath, channel=1, frame_start=1)
            context.scene.sequence_editor.sequences.new_sound(name='ThreePoint Temp Sound', filepath=filepath, channel=2, frame_start=1)
            context.scene.frame_start = self.in_frame
            context.scene.frame_end = self.out_frame
            context.scene.frame_current = self.in_frame + 1
            args = (self, context)
            self._handle = bpy.types.SpaceClipEditor.draw_handler_add(three_point_draw_callback, args, 'WINDOW', 'POST_PIXEL')
            context.window_manager.modal_handler_add(self)

            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}


#Functions and classes related to grabs and selections
def vseqf_grab_draw(self, context):
    #Callback function to draw overlays in sequencer when grab is activated
    colors = context.user_preferences.themes[0].user_interface
    text_color = list(colors.wcol_text.text_sel)+[1]
    if self.ripple:
        mode = 'Ripple'
        if self.ripple_pop:
            mode = 'Ripple-Pop'
    else:
        mode = 'Grab'

    view = context.region.view2d
    for seq in self.grabbed_sequences:
        sequence = seq[0]
        window_x, window_y = view.view_to_region(sequence.frame_final_start, sequence.channel)
        draw_text(window_x, window_y, 12, mode, text_color)


class VSEQFGrabAdd(bpy.types.Operator):
    """Modal operator designed to run in tandem with the built-in grab operator."""
    bl_idname = "vseqf.grabadd"
    bl_label = "Runs in tandem with the grab operator in the vse, adds functionality."

    grabbed_sequences = []
    grabbed_names = []
    target_grab_sequence = None
    target_grab_variable = ''
    target_grab_start = 0
    target_grab_channel = 1
    sequences = []
    pos_x_start = 0
    pos_y_start = 0
    pos_x = 0
    pos_y = 0
    ripple = False
    ripple_pop = False
    can_pop = False
    alt_pressed = False
    view2d = None
    prefs = None
    _timer = None
    _handle = None
    cancelled = False
    start_frame = 0
    snap_edge = None

    def find_by_name(self, name):
        #finds the sequence data matching the given name.
        for seq in self.grabbed_sequences:
            if seq[0].name == name:
                return seq
        return False

    def find_by_sequence(self, sequence):
        for seq in self.sequences:
            if seq[0] == sequence:
                return seq
        return False

    def sequencer_used_height(self, left, right):
        #determines the highest and lowest used channel in the sequencer in the given frame range.
        sequences = self.sequences
        top = 0
        bottom = 0
        for seq in sequences:
            start = seq[1]
            end = seq[2]
            if (start > left and start < right) or (end > left and end < right) or (start < left and end > right):
                if bottom == 0:
                    bottom = seq[4]
                elif seq[4] < bottom:
                    bottom = seq[4]
                if seq[4] > top:
                    top = seq[4]
        return [bottom, top]

    def sequencer_area_filled(self, left, right, bottom, top):
        #returns False if the given area of the sequencer is open, True if a sequence is there
        if bottom > top:
            old_top = top
            top = bottom
            bottom = old_top
        sequences = self.sequences
        for seq in sequences:
            if seq[4] > bottom and seq[4] < top:
                start = seq[1]
                end = seq[2]
                if (start > left and start < right) or (end > left and end < right) or (start < left and end > right):
                    return True
        return False

    def sequencer_area_clear(self, left, right, bottom, top):
        del bottom
        del top
        #checks if strips ahead of the given area can fit in the given area
        width = right - left
        max_bottom, max_top = self.sequencer_used_height(right, right+1+width)
        if not self.sequencer_area_filled(left, right, max_bottom, max_top):
            return True
        return False

    def move_sequences(self, offset_x, offset_y, all=False):
        ripple_offset = 0
        ripple_start = self.sequences[0][1]

        for seq in self.sequences:
            sequence = seq[0]
            if not sequence.lock:
                if not hasattr(sequence, 'input_1'):
                    if sequence.select:
                        #if ripple is enabled, this sequence will affect the position of all sequences after it
                        if self.ripple:
                            if sequence.select_left_handle and not sequence.select_right_handle and len(self.grabbed_sequences) == 1:
                                #special ripple slide if only one sequence and left handle grabbed
                                sequence.frame_start = seq[3]
                                frame_start = seq[1]
                                ripple_offset = ripple_offset + frame_start - sequence.frame_final_start
                                sequence.frame_start = seq[3] + ripple_offset
                            else:
                                if self.ripple_pop and sequence.channel != seq[4] and self.sequencer_area_clear(seq[0].frame_final_start, seq[0].frame_final_end, seq[4], sequence.channel):
                                    #ripple 'pop'
                                    ripple_start = seq[1]
                                    ripple_offset = sequence.frame_final_duration
                                    ripple_offset = 0 - ripple_offset
                                else:
                                    ripple_start = seq[1]
                                    ripple_offset = seq[2] - sequence.frame_final_end
                                    ripple_offset = 0 - ripple_offset
                        elif sequence.select_left_handle and not sequence.select_right_handle:
                            #fix sequence left handle ripple position when not rippled
                            sequence.frame_start = seq[3]
                        if sequence.select_left_handle or sequence.select_right_handle:
                            #make sequences that are having the handles adjusted behave better
                            new_channel = seq[4]
                            new_start = sequence.frame_final_start
                            new_end = sequence.frame_final_end
                            if sequence.select_left_handle and sequence.select_right_handle and sequence.type in ['MOVIE', 'SCENE', 'MOVIECLIP']:
                                if sequence.frame_duration - sequence.frame_offset_start == 1:
                                    #sequence has been slipped beyond the right edges it can be, try to fix
                                    duration = seq[2] - seq[1]
                                    new_end = sequence.frame_final_start + duration
                                    sequence.frame_final_end = new_end
                                if sequence.frame_duration - sequence.frame_offset_end == 1:
                                    #sequence has been slipped beyond the left edges it can be, try to fix
                                    duration = seq[2] - seq[1]
                                    new_start = sequence.frame_final_end - duration
                                    sequence.frame_final_start = new_start
                            while sequencer_area_filled(new_start, new_end, new_channel, new_channel, [sequence]):
                                new_channel = new_channel + 1
                            sequence.channel = new_channel
                    else:  #not selected
                        if seq[9]:
                            #this sequence has a parent that may be moved
                            new_start = seq[1]
                            new_end = seq[2]
                            new_pos = seq[3]
                            if sequence.parent in self.grabbed_names:
                                #this sequence's parent is selected
                                parent_data = self.find_by_name(sequence.parent)
                                parent = parent_data[0]
                                #new_channel = seq[4] + (parent_data[0].channel - parent_data[4])
                                new_channel = seq[4] + offset_y
                                if self.ripple and seq[1] > ripple_start:
                                    seq[8] = True
                                    new_pos = new_pos + ripple_offset
                                    new_start = new_start + ripple_offset
                                    new_end = new_end + ripple_offset
                                else:
                                    if parent_data[3] != parent.frame_start:
                                        #parent was moved, move child too
                                        offset = parent.frame_start - parent_data[3]
                                        new_pos = new_pos + offset
                                        new_start = new_start + offset
                                        new_end = new_end + offset
                                    if parent_data[0].select_left_handle and parent_data[1] == seq[1]:
                                        #parent sequence's left edge was changed, child's edge should match it
                                        new_start = parent.frame_final_start
                                    if parent_data[0].select_right_handle and parent_data[2] == seq[2]:
                                        #parent sequence's right edge was changed, child's edge should match it
                                        new_end = parent.frame_final_end
                            else:
                                #this is a child of a child, just move it the same amount that the grab is moved
                                new_channel = seq[4] + offset_y
                                new_start = seq[1] + offset_x
                                new_end = seq[2] + offset_x
                                new_pos = seq[3] + offset_x
                            #if new_end != sequence.frame_final_end or new_start != sequence.frame_final_start:
                            while sequencer_area_filled(new_start, new_end, new_channel, new_channel, [sequence]):
                                new_channel = new_channel + 1
                            sequence.channel = new_channel
                            sequence.frame_start = new_pos
                            sequence.frame_final_start = new_start
                            sequence.frame_final_end = new_end
                        else:
                            #unparented, unselected sequences - need to ripple if enabled
                            if self.ripple and (seq[1] >= ripple_start):
                                seq[8] = True
                                new_channel = seq[4]
                                while sequencer_area_filled(seq[1] + ripple_offset, seq[2] + ripple_offset, new_channel, new_channel, [sequence]):
                                    new_channel = new_channel + 1
                                sequence.channel = new_channel
                                sequence.frame_start = seq[3] + ripple_offset
                    if seq[8] and not self.ripple:
                        #fix sequence locations when ripple is disabled
                        new_channel = seq[4]
                        new_start = seq[1]
                        new_end = seq[2]
                        while sequencer_area_filled(new_start, new_end, new_channel, new_channel, [sequence]):
                            new_channel = new_channel + 1
                        sequence.channel = new_channel
                        sequence.frame_start = seq[3]
                        if sequence.frame_start == seq[3] and sequence.channel == seq[4]:
                            #unfortunately, there seems to be a limitation in blender preventing me from putting the strip back where it should be... keep trying until the grabbed strips are out of the way.
                            seq[8] = False
                else:
                    #effect strip, just worry about changing the channel if it belongs to a selected sequence
                    input_1 = sequence.input_1
                    new_channel = False
                    if hasattr(sequence, 'input_2'):
                        input_2 = sequence.input_2
                    else:
                        input_2 = False
                    input_1_data = self.find_by_sequence(input_1)
                    if input_1_data:
                        input_1_channel_offset = input_1_data[0].channel - input_1_data[4]
                        if input_1_channel_offset == 0 and input_2:
                            input_2_data = self.find_by_sequence(input_2)
                            if input_2_data:
                                input_2_channel_offset = input_2_data[0].channel - input_2_data[4]
                                if input_2_channel_offset != 0:
                                    new_channel = seq[4] + input_2_channel_offset
                        else:
                            new_channel = seq[4] + input_1_channel_offset
                    if new_channel is not False:
                        sequence.channel = new_channel

    def modal(self, context, event):
        if event.type == 'TIMER':
            pass
        if event.alt:
            self.alt_pressed = True
        else:
            if self.alt_pressed:
                if self.can_pop:
                    self.alt_pressed = False
                    if self.ripple and self.ripple_pop:
                        self.ripple = False
                        self.ripple_pop = False
                    elif self.ripple:
                        self.ripple_pop = True
                    else:
                        self.ripple = True
                else:
                    self.alt_pressed = False
                    self.ripple = not self.ripple
                    self.ripple_pop = False

        if self.snap_edge:
            if self.snap_edge == 'left':
                frame = self.grabbed_sequences[0][0].frame_final_start
            else:
                frame = self.grabbed_sequences[0][0].frame_final_end - 1
            context.scene.frame_current = frame
        pos_x = 0
        pos_y = self.target_grab_sequence.channel
        if self.target_grab_variable == 'frame_start':
            pos_x = self.target_grab_sequence.frame_start
        elif self.target_grab_variable == 'frame_final_start':
            pos_x = self.target_grab_sequence.frame_final_start
        elif self.target_grab_variable == 'frame_final_end':
            pos_x = self.target_grab_sequence.frame_final_end
        offset_x = pos_x - self.target_grab_start
        if self.target_grab_sequence.select_left_handle or self.target_grab_sequence.select_right_handle:
            offset_y = 0
        else:
            offset_y = pos_y - self.target_grab_channel

        self.move_sequences(offset_x, offset_y)

        if event.type in {'LEFTMOUSE', 'RET'}:
            self.remove_draw_handler()
            self.move_sequences(offset_x, offset_y, all=True)  #check sequences one last time, just to be sure
            for seq in self.sequences:
                sequence = seq[0]
                if self.prefs.fades:
                    #Fix fades in sequence if they exist
                    if sequence.frame_final_start != seq[1]:
                        #fix fade in
                        fade_in = fades(sequence, mode='detect', direction='in', fade_low_point_frame=seq[1])
                        if fade_in > 0:
                            fades(sequence, mode='set', direction='in', fade_length=fade_in)
                    if sequence.frame_final_end != seq[2]:
                        #fix fade out
                        fade_out = fades(sequence, mode='detect', direction='out', fade_low_point_frame=seq[2])
                        if fade_out > 0:
                            fades(sequence, mode='set', direction='out', fade_length=fade_out)
            if not context.screen.is_animation_playing and self.snap_edge:
                context.scene.frame_current = self.start_frame
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            #cancel movement and put everything back
            if not self.cancelled:
                self.cancelled = True
                current_frame = context.scene.frame_current
                bpy.ops.ed.undo()
                if not context.screen.is_animation_playing:
                    context.scene.frame_current = self.start_frame
                else:
                    if context.scene.frame_current != current_frame:
                        bpy.ops.screen.animation_play()
                        context.scene.frame_current = current_frame
                        bpy.ops.screen.animation_play()
                self.remove_draw_handler()
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def remove_draw_handler(self):
        bpy.types.SpaceSequenceEditor.draw_handler_remove(self._handle, 'WINDOW')

    def get_sequence_data(self, sequence):
        # store original data:
        #   0 strip
        #   1 frame_final_start - controlled by left handle
        #   2 frame_final_end - controlled by right handle
        #   3 frame_start - position
        #   4 channel
        #   5 select
        #   6 select_left_handle
        #   7 select_right_handle
        #   8 rippled
        #   9 child
        return [sequence, sequence.frame_final_start, sequence.frame_final_end, sequence.frame_start, sequence.channel, sequence.select, sequence.select_left_handle, sequence.select_right_handle, False, False]

    def invoke(self, context, event):
        self.start_frame = context.scene.frame_current
        bpy.ops.ed.undo_push()
        self.cancelled = False
        self.prefs = get_prefs()
        region = context.region
        self.view2d = region.view2d
        self.pos_x, self.pos_y = self.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        self.pos_x_start = self.pos_x
        self.pos_y_start = self.pos_y
        self.sequences = []
        self.grabbed_sequences = []
        self.grabbed_names = []
        parenting = vseqf_parenting()
        to_move = []
        selected_sequences = current_selected(context)
        for seq in selected_sequences:
            if parenting:
                if not (seq.select_left_handle or seq.select_right_handle):
                    to_move = get_recursive(seq, to_move)
                else:
                    to_move.append(seq)
                    children = find_children(seq)
                    to_move.extend(children)
            else:
                to_move.append(seq)
        sequences = current_sequences(context)
        for seq in sequences:
            sequence_data = self.get_sequence_data(seq)
            if parenting and seq in to_move:
                sequence_data[9] = True
            if seq.select:
                self.grabbed_names.append(seq.name)
                self.grabbed_sequences.append(sequence_data)
            else:
                self.sequences.append(sequence_data)
        self._timer = context.window_manager.event_timer_add(0.01, context.window)
        self.sequences.sort(key=lambda x: x[1])
        self.grabbed_sequences.sort(key=lambda x: x[1])
        self.sequences = self.grabbed_sequences + self.sequences  #ensure that the grabbed sequences are processed first to prevent issues with ripple
        grabbed_left = False
        grabbed_right = False
        grabbed_center = False
        for seq in self.grabbed_sequences:
            sequence = seq[0]
            if seq[5] and not (seq[6] or seq[7]):
                grabbed_center = sequence
            else:
                if seq[6]:
                    grabbed_left = sequence
                if seq[7]:
                    grabbed_right = sequence
        if grabbed_center:
            self.target_grab_variable = 'frame_start'
            self.target_grab_sequence = grabbed_center
            self.target_grab_start = grabbed_center.frame_start
            self.target_grab_channel = grabbed_center.channel
        else:
            if grabbed_right:
                self.target_grab_variable = 'frame_final_end'
                self.target_grab_sequence = grabbed_right
                self.target_grab_start = grabbed_right.frame_final_end
                self.target_grab_channel = grabbed_right.channel
            if grabbed_left:
                self.target_grab_variable = 'frame_final_start'
                self.target_grab_sequence = grabbed_left
                self.target_grab_start = grabbed_left.frame_final_start
                self.target_grab_channel = grabbed_left.channel
        self.snap_edge = None
        if len(self.grabbed_sequences) == 1:
            #only one sequence grabbed
            if (grabbed_right and not grabbed_left) or (grabbed_left and not grabbed_right):
                #Only one edge grabbed, use cursor snap to edge mode
                if not context.screen.is_animation_playing and context.scene.vseqf.snap_cursor_to_edge:
                    if grabbed_right:
                        self.snap_edge = 'right'
                    else:
                        self.snap_edge = 'left'
        if not self.target_grab_sequence:
            #nothing selected... is this possible?
            return {'CANCELLED'}
        if len(self.grabbed_sequences) == 1 and not (self.grabbed_sequences[0][0].select_left_handle or self.grabbed_sequences[0][0].select_right_handle):
            self.can_pop = True
        else:
            self.can_pop = False
        context.window_manager.modal_handler_add(self)
        args = (self, context)
        self._handle = bpy.types.SpaceSequenceEditor.draw_handler_add(vseqf_grab_draw, args, 'WINDOW', 'POST_PIXEL')
        return {'RUNNING_MODAL'}


class VSEQFGrab(bpy.types.Operator):
    """Wrapper operator for the built-in grab operator, runs the added features as well as the original."""
    bl_idname = "vseqf.grab"
    bl_label = "Replacement for the default grab operator with more features"

    mode = bpy.props.StringProperty("")

    def execute(self, context):
        del context
        bpy.ops.vseqf.grabadd('INVOKE_DEFAULT')
        if self.mode == "TIME_EXTEND":
            bpy.ops.transform.transform("INVOKE_DEFAULT", mode=self.mode)
        elif self.mode == "SLIP":
            bpy.ops.sequencer.slip('INVOKE_DEFAULT')
        else:
            bpy.ops.transform.seq_slide('INVOKE_DEFAULT')
        self.mode = ''
        return {'FINISHED'}


class VSEQFSelectGrab(bpy.types.Operator):
    """Replacement for the right-click select operator"""
    bl_idname = "vseqf.select_grab"
    bl_label = "Replacement for the sequncer.tf_select operator"

    mouse_start_x = 0
    mouse_start_y = 0
    selected = []
    start_time = 0
    _timer = None

    def on_sequence(self, frame, channel, sequence):
        if frame >= sequence.frame_final_start and frame <= sequence.frame_final_end and int(channel) == sequence.channel:
            return True
        else:
            return False

    def near_marker(self, context, frame, distance):
        for marker in context.scene.timeline_markers:
            if abs(marker.frame - frame) <= distance:
                return marker
        return None

    def modal(self, context, event):
        run_time = time.time() - self.start_time
        region = context.region
        view = region.view2d
        distance_multiplier = 15
        if context.scene.vseqf.context and run_time > right_click_time:
            location = view.region_to_view(event.mouse_region_x, event.mouse_region_y)
            click_frame, click_channel = location
            self.restore_selected()
            active = current_active(context)

            #determine distance scale
            width = region.width
            left, bottom = view.region_to_view(0, 0)
            right, bottom = view.region_to_view(width, 0)
            shown_width = right - left
            frame_px = width / shown_width
            distance = distance_multiplier / frame_px
            near_marker = self.near_marker(context, click_frame, distance)

            if abs(click_frame - context.scene.frame_current) <= distance:
                #clicked on cursor
                bpy.ops.wm.call_menu(name='vseqf.context_cursor')
            elif near_marker:
                #clicked on marker
                context.scene.vseqf.current_marker_frame = near_marker.frame
                bpy.ops.wm.call_menu(name='vseqf.context_marker')
            elif active and self.on_sequence(click_frame, click_channel, active):
                #clicked on sequence
                active_size = active.frame_final_duration * frame_px
                if abs(click_frame - active.frame_final_start) <= distance * 2 and active_size > 60:
                    bpy.ops.wm.call_menu(name='vseqf.context_sequence_left')
                elif abs(click_frame - active.frame_final_end) <= distance * 2 and active_size > 60:
                    bpy.ops.wm.call_menu(name='vseqf.context_sequence_right')
                else:
                    bpy.ops.wm.call_menu(name="vseqf.context_sequence")
            else:
                #clicked on empty area
                bpy.ops.wm.call_menu(name='vseqf.context_none')
            return {'FINISHED'}
        move_target = 10
        if event.type == 'MOUSEMOVE':
            delta_x = abs(self.mouse_start_x - event.mouse_x)
            delta_y = abs(self.mouse_start_y - event.mouse_y)
            if delta_x > move_target or delta_y > move_target:
                if context.scene.vseqf.grab_multiselect:
                    self.restore_selected()
                location = view.region_to_view(event.mouse_region_x, event.mouse_region_y)
                click_frame, click_channel = location
                width = region.width
                left, bottom = view.region_to_view(0, 0)
                right, bottom = view.region_to_view(width, 0)
                shown_width = right - left
                frame_px = width / shown_width
                distance = distance_multiplier / frame_px
                near_marker = self.near_marker(context, click_frame, distance)
                if near_marker:
                    bpy.ops.vseqf.quickmarkers_move(frame=near_marker.frame)
                else:
                    bpy.ops.vseqf.grab('INVOKE_DEFAULT')
                return {'FINISHED'}
            else:
                return {'RUNNING_MODAL'}
        elif event.type in {'TIMER', 'TIMER0', 'TIMER1', 'TIMER2', 'TIMER_JOBS', 'TIMER_AUTOSAVE', 'TIMER_REPORT', 'TIMERREGION', 'NONE', 'INBETWEEN_MOUSEMOVE'}:
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}

    def restore_selected(self):
        for data in self.selected:
            sequence, select_left, select_right = data
            sequence.select = True
            if select_left:
                sequence.select_left_handle = True
            if select_right:
                sequence.select_right_handle = True

    def execute(self, context):
        del context
        return {'FINISHED'}

    def invoke(self, context, event):
        bpy.ops.ed.undo_push()
        self.start_time = time.time()
        self.selected = []
        selected_sequences = current_selected(context)
        for sequence in selected_sequences:
            self.selected.append([sequence, sequence.select_left_handle, sequence.select_right_handle])
        bpy.ops.sequencer.select('INVOKE_DEFAULT')
        prefs = get_prefs()
        if prefs.threepoint:
            active = current_active(context)
            if active and active.type == 'MOVIE':
                #look for a clip editor area and set the active clip to the selected sequence if one exists that shares the same source.
                newclip = None
                for clip in bpy.data.movieclips:
                    if os.path.normpath(bpy.path.abspath(clip.filepath)) == os.path.normpath(bpy.path.abspath(active.filepath)):
                        newclip = clip
                        break
                if newclip:
                    for area in context.screen.areas:
                        if area.type == 'CLIP_EDITOR':
                            area.spaces[0].clip = newclip

        if context.scene.vseqf.select_children:
            to_select = []
            for sequence in selected_sequences:
                to_select = get_recursive(sequence, to_select)
                for seq in to_select:
                    seq.select = sequence.select
                    seq.select_left_handle = sequence.select_left_handle
                    seq.select_right_handle = sequence.select_right_handle
        self.mouse_start_x = event.mouse_x
        self.mouse_start_y = event.mouse_y
        self._timer = context.window_manager.event_timer_add(0.05, context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


class VSEQFContextMarker(bpy.types.Menu):
    bl_idname = 'vseqf.context_marker'
    bl_label = 'Marker Operations'

    def draw(self, context):
        layout = self.layout
        layout.operator('ed.undo', text='Undo')
        layout.separator()
        frame = context.scene.vseqf.current_marker_frame
        marker = None
        for timeline_marker in context.scene.timeline_markers:
            if timeline_marker.frame == frame:
                marker = timeline_marker
        if marker:
            layout.operator('vseqf.quickmarkers_delete', text='Delete Marker').frame = frame
            row = layout.row()
            row.operator_context = 'INVOKE_DEFAULT'
            row.operator('vseqf.quickmarkers_rename')
            layout.operator('vseqf.quickmarkers_jump', text='Jump Cursor To This Marker').frame = frame
            layout.operator('vseqf.quickmarkers_move').frame = frame


class VSEQFContextCursor(bpy.types.Menu):
    bl_idname = "vseqf.context_cursor"
    bl_label = "Cursor Operations"

    def draw(self, context):
        layout = self.layout
        layout.operator('ed.undo', text='Undo')
        layout.separator()
        props = layout.operator("sequencer.strip_jump", text="Jump to Previous Strip")
        props.next = False
        props.center = False
        props = layout.operator("sequencer.strip_jump", text="Jump to Next Strip")
        props.next = True
        props.center = False
        layout.separator()
        layout.label('Snap:')
        layout.operator('vseqf.quicksnaps', text='Cursor To Nearest Second').type = 'cursor_to_seconds'
        sequence = current_active(context)
        if sequence:
            layout.operator('vseqf.quicksnaps', text='Cursor To Beginning Of Sequence').type = 'cursor_to_beginning'
            layout.operator('vseqf.quicksnaps', text='Cursor To End Of Sequence').type = 'cursor_to_end'
            layout.operator('vseqf.quicksnaps', text='Selected To Cursor').type = 'selection_to_cursor'
            layout.operator('vseqf.quicksnaps', text='Sequence Beginning To Cursor').type = 'begin_to_cursor'
            layout.operator('vseqf.quicksnaps', text='Sequence End To Cursor').type = 'end_to_cursor'


class VSEQFContextNone(bpy.types.Menu):
    bl_idname = 'vseqf.context_none'
    bl_label = "Operations On Sequence Editor"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator('ed.undo', text='Undo')
        layout.separator()
        layout.menu('SEQUENCER_MT_add')
        layout.menu('vseqf.quickzooms_menu')


class VSEQFContextSequenceLeft(bpy.types.Menu):
    bl_idname = "vseqf.context_sequence_left"
    bl_label = "Operations On Left Handle"

    def draw(self, context):
        strip = current_active(context)
        layout = self.layout
        layout.operator('ed.undo', text='Undo')
        if strip:
            layout.separator()
            layout.prop(context.scene.vseqf, 'fade')
            layout.operator('vseqf.quickfades_set', text='Set Fade In').type = 'in'
            props = layout.operator('vseqf.quickfades_clear', text='Clear Fade In')
            props.direction = 'in'
            props.active_only = True


class VSEQFContextSequenceRight(bpy.types.Menu):
    bl_idname = "vseqf.context_sequence_right"
    bl_label = "Operations On Right Handle"

    def draw(self, context):
        strip = current_active(context)
        layout = self.layout
        layout.operator('ed.undo', text='Undo')
        if strip:
            layout.separator()
            layout.prop(context.scene.vseqf, 'fade')
            layout.operator('vseqf.quickfades_set', text='Set Fade Out').type = 'out'
            props = layout.operator('vseqf.quickfades_clear', text='Clear Fade Out')
            props.direction = 'out'
            props.active_only = True


class VSEQFContextSequence(bpy.types.Menu):
    bl_idname = "vseqf.context_sequence"
    bl_label = "Operations On Sequence"

    def draw(self, context):
        prefs = get_prefs()
        strip = current_active(context)
        selected = current_selected(context)
        layout = self.layout
        layout.operator('ed.undo', text='Undo')
        if strip:
            layout.separator()
            layout.label('Active Sequence:')
            layout.prop(strip, 'mute')
            layout.prop(strip, 'lock')
            if prefs.tags:
                layout.menu('vseqf.quicktags_menu')
        if selected:
            layout.separator()
            if prefs.cuts:
                layout.menu('vseqf.quickcuts_menu')
            if prefs.parenting:
                layout.menu('vseqf.quickparents_menu')
            layout.operator('sequencer.duplicate_move', text='Duplicate')
            layout.operator('vseqf.grab', text='Grab/Move')


#Functions related to QuickSpeed
@persistent
def frame_step(scene):
    """Handler that skips frames when the speed step value is used
    Argument:
        scene: the current Scene"""

    if bpy.context.screen.scene != scene:
        return
    step = abs(scene.vseqf.step) - 1
    difference = scene.frame_current - scene.vseqf.last_frame
    if difference == -1 or difference == 1:
        if step == 1:
            #Skip every 4th frame
            if scene.frame_current % 4 == 0:
                scene.frame_current = scene.frame_current + difference
        if step == 2:
            #Skip every 3rd frame
            if scene.frame_current % 3 == 0:
                scene.frame_current = scene.frame_current + difference
        if step > 2:
            #Skip step - 1 frames
            scene.frame_current = scene.frame_current + (difference * (step - 1))
    scene.vseqf.last_frame = scene.frame_current


def draw_quickspeed_header(self, context):
    """Draws the speed selector in the sequencer header"""
    layout = self.layout
    scene = context.scene
    self.layout_width = 30
    layout.prop(scene.vseqf, 'step', text="Speed Step")


#Functions and classes related to QuickZoom
def draw_follow_header(self, context):
    layout = self.layout
    scene = context.scene
    layout.prop(scene.vseqf, 'follow', text='Follow Cursor', toggle=True)


def start_follow(_, context):
    if context.scene.vseqf.follow:
        bpy.ops.vseqf.follow('INVOKE_DEFAULT')


def draw_quickzoom_menu(self, context):
    """Draws the submenu for the QuickZoom shortcuts, placed in the sequencer view menu"""
    del context
    layout = self.layout
    layout.menu('vseqf.quickzooms_menu', text="Quick Zoom")


def zoom_custom(begin, end, bottom=None, top=None, preroll=True):
    """Zooms to an area on the sequencer timeline by adding a temporary strip, zooming to it, then deleting that strip.
    Note that this function will retain selected and active sequences.
    Arguments:
        begin: The starting frame of the zoom area
        end: The ending frame of the zoom area
        bottom: The lowest visible channel
        top: The topmost visible channel
        preroll: If true, add a buffer before the beginning"""

    scene = bpy.context.scene
    selected = []

    #Find sequence editor, or create if not found
    try:
        sequences = bpy.context.sequences
    except:
        scene.sequence_editor_create()
        sequences = bpy.context.sequences

    #Save selected sequences and active strip because they will be overwritten
    for sequence in sequences:
        if sequence.select:
            selected.append(sequence)
            sequence.select = False
    active = current_active(bpy.context)

    begin = int(begin)
    end = int(end)

    #Determine preroll for the zoom
    zoomlength = end - begin
    if zoomlength > 60 and preroll:
        preroll = (zoomlength-60) / 10
    else:
        preroll = 0

    #Create a temporary sequence, zoom in on it, then delete it
    zoom_clip = scene.sequence_editor.sequences.new_effect(name='----vseqf-temp-zoom----', type='ADJUSTMENT', channel=1, frame_start=begin-preroll, frame_end=end)
    scene.sequence_editor.active_strip = zoom_clip
    for region in bpy.context.area.regions:
        if region.type == 'WINDOW':
            override = {'region': region, 'window': bpy.context.window, 'screen': bpy.context.screen, 'area': bpy.context.area, 'scene': bpy.context.scene}
            bpy.ops.sequencer.view_selected(override)
    bpy.ops.sequencer.delete()

    #Reset selected sequences and active strip
    for sequence in selected:
        sequence.select = True
    if active:
        bpy.context.scene.sequence_editor.active_strip = active


def zoom_cursor(self=None, context=None):
    """Zooms near the cursor based on the 'zoom_size' vseqf variable"""
    del self
    del context
    cursor = bpy.context.scene.frame_current
    zoom_custom(cursor, (cursor + bpy.context.scene.vseqf.zoom_size))


class VSEQFQuickZoomsMenu(bpy.types.Menu):
    """Pop-up menu for sequencer zoom shortcuts"""
    bl_idname = "vseqf.quickzooms_menu"
    bl_label = "Quick Zooms"

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        layout.operator('vseqf.quickzooms', text='Zoom All Strips').area = 'all'
        layout.operator('vseqf.quickzooms', text='Zoom To Timeline').area = 'timeline'
        selected_sequences = current_selected(bpy.context)
        if len(selected_sequences) > 0:
            #Only show if a sequence is selected
            layout.operator('vseqf.quickzooms', text='Zoom Selected').area = 'selected'

        layout.operator('vseqf.quickzooms', text='Zoom Cursor').area = 'cursor'
        layout.prop(scene.vseqf, 'zoom_size', text="Size")
        layout.operator('vseqf.quickzoom_add', text='Save Current Zoom')
        if len(scene.vseqf.zoom_presets) > 0:
            layout.menu('vseqf.quickzoom_preset_menu')

        layout.separator()
        layout.operator('vseqf.quickzooms', text='Zoom 2 Seconds').area = '2'
        layout.operator('vseqf.quickzooms', text='Zoom 10 Seconds').area = '10'
        layout.operator('vseqf.quickzooms', text='Zoom 30 Seconds').area = '30'
        layout.operator('vseqf.quickzooms', text='Zoom 1 Minute').area = '60'
        layout.operator('vseqf.quickzooms', text='Zoom 2 Minutes').area = '120'
        layout.operator('vseqf.quickzooms', text='Zoom 5 Minutes').area = '300'
        layout.operator('vseqf.quickzooms', text='Zoom 10 Minutes').area = '600'


class VSEQFQuickZoomPresetMenu(bpy.types.Menu):
    """Menu for saved zoom presets"""
    bl_idname = "vseqf.quickzoom_preset_menu"
    bl_label = "Zoom Presets"

    def draw(self, context):
        del context
        scene = bpy.context.scene
        vseqf = scene.vseqf
        layout = self.layout
        split = layout.split()
        column = split.column()
        for zoom in vseqf.zoom_presets:
            column.operator('vseqf.quickzoom_preset', text=zoom.name).name = zoom.name
        column.separator()
        column.operator('vseqf.quickzoom_clear', text='Clear All')
        column = split.column()
        for zoom in vseqf.zoom_presets:
            column.operator('vseqf.quickzoom_remove', text='X').name = zoom.name


class VSEQFQuickZoomPreset(bpy.types.Operator):
    """Zooms to a specific preset, given by name.
    Argument:
        name: String, the zoom preset to activate"""

    bl_idname = 'vseqf.quickzoom_preset'
    bl_label = "Zoom To QuickZoom Preset"

    name = bpy.props.StringProperty()

    def execute(self, context):
        vseqf = context.scene.vseqf
        for zoom in vseqf.zoom_presets:
            if zoom.name == self.name:
                zoom_custom(zoom.left, zoom.right, bottom=zoom.bottom, top=zoom.top, preroll=False)
                break
        return {'FINISHED'}


class VSEQFClearZooms(bpy.types.Operator):
    """Clears all zoom presets"""

    bl_idname = 'vseqf.quickzoom_clear'
    bl_label = 'Clear All Presets'

    def execute(self, context):
        vseqf = context.scene.vseqf
        bpy.ops.ed.undo_push()
        for index, zoom_preset in reversed(list(enumerate(vseqf.zoom_presets))):
            vseqf.zoom_presets.remove(index)
        return{'FINISHED'}


class VSEQFRemoveZoom(bpy.types.Operator):
    """Removes a zoom from the preset list

    Argument:
        name: String, the name of the zoom preset to be removed"""

    bl_idname = 'vseqf.quickzoom_remove'
    bl_label = 'Remove Zoom Preset'

    name = bpy.props.StringProperty()

    def execute(self, context):
        vseqf = context.scene.vseqf
        for index, zoom_preset in reversed(list(enumerate(vseqf.zoom_presets))):
            if zoom_preset.name == self.name:
                bpy.ops.ed.undo_push()
                vseqf.zoom_presets.remove(index)
        return{'FINISHED'}


class VSEQFAddZoom(bpy.types.Operator):
    """Stores the current vse zoom and position
    Argument:
        mode: String, determines where the preset is stored."""

    bl_idname = 'vseqf.quickzoom_add'
    bl_label = "Add Zoom Preset"

    mode = bpy.props.StringProperty()

    def execute(self, context):
        left, right, bottom, top = get_vse_position(context)
        vseqf = context.scene.vseqf
        #name = "Frames "+str(int(round(left)))+'-'+str(int(round(right)))+', Channels '+str(int(round(bottom)))+'-'+str(int(round(top)))
        name = "Frames "+str(int(round(left)))+'-'+str(int(round(right)))
        bpy.ops.ed.undo_push()
        for index, zoom_preset in enumerate(vseqf.zoom_presets):
            if zoom_preset.name == name:
                vseqf.zoom_presets.move(index, len(vseqf.zoom_presets) - 1)
                return{'FINISHED'}
        preset = vseqf.zoom_presets.add()
        preset.name = name
        preset.left = left
        preset.right = right
        preset.bottom = bottom
        preset.top = top
        return{'FINISHED'}


class VSEQFQuickZooms(bpy.types.Operator):
    """Wrapper operator for zooming the sequencer in different ways
    Argument:
        area: String, determines the zoom method, can be set to:
            all: calls bpy.ops.sequencer.view_all()
            selected: calls bpy.ops.sequencer.view_selected()
            cursor: calls the zoom_cursor() function
            numerical value: zooms to the number of seconds given in the value"""
    bl_idname = 'vseqf.quickzooms'
    bl_label = 'VSEQF Quick Zooms'
    bl_description = 'Changes zoom level of the sequencer timeline'

    #Should be set to 'all', 'selected', cursor', or a positive number of seconds
    area = bpy.props.StringProperty()

    def execute(self, context):
        if self.area.isdigit():
            #Zoom value is a number of seconds
            scene = context.scene
            cursor = scene.frame_current
            zoom_custom(cursor, (cursor + ((scene.render.fps/scene.render.fps_base) * int(self.area))))
        elif self.area == 'timeline':
            scene = context.scene
            zoom_custom(scene.frame_start, scene.frame_end)
        elif self.area == 'all':
            bpy.ops.sequencer.view_all()
        elif self.area == 'selected':
            bpy.ops.sequencer.view_selected()
        elif self.area == 'cursor':
            zoom_cursor()
        return{'FINISHED'}


class VSEQFFollow(bpy.types.Operator):
    """Modal operator that will center on the play cursor while running."""
    bl_idname = "vseqf.follow"
    bl_label = "Center the playcursor"
    region = None
    view = None

    _timer = None

    def modal(self, context, event):
        region = self.region
        view = self.view
        if not context.scene.vseqf.follow:
            return {'CANCELLED'}

        if event.type == 'TIMER':
            override = context.copy()
            override['region'] = self.region
            override['view2d'] = self.view
            cursor_target = round(region.width / 4)
            cursor_location = (view.view_to_region(context.scene.frame_current, 0, clip=False))[0]
            if cursor_location != 12000:
                offset = (cursor_target - cursor_location)
                bpy.ops.view2d.pan(override, deltax=-offset)
        #if event.type in {'RIGHTMOUSE', 'ESC'}:
        #    return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        del event
        area = context.area
        for region in area.regions:
            if region.type == 'WINDOW':
                self.region = region
                self.view = region.view2d
        if self.region is None or self.view is None:
            return {'CANCELLED'}
        self._timer = context.window_manager.event_timer_add(0.5, context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


#Functions and classes related to QuickFades
def vseqf_crossfade(first_sequence, second_sequence):
    """Add a crossfade between two sequences, the transition type is determined by the vseqf variable 'transition'
    Arguments:
        first_sequence: VSE Sequence object being transitioned from
        second_sequence: VSE Sequence object being transitioned to"""

    transition_type = bpy.context.scene.vseqf.transition
    frame_start = first_sequence.frame_final_end
    frame_end = second_sequence.frame_final_start
    channel = first_sequence.channel
    while sequencer_area_filled(frame_start, frame_end, channel, channel, []):
        channel = channel + 1
    bpy.context.scene.sequence_editor.sequences.new_effect(name=transition_type, type=transition_type, channel=channel,  frame_start=frame_start, frame_end=frame_end, seq1=first_sequence, seq2=second_sequence)


def fades(sequence, mode, direction, fade_length=0, fade_low_point_frame=False):
    """Detects, creates, and edits fadein and fadeout for sequences.
    Arguments:
        sequence: VSE Sequence object that will be operated on
        mode: String, determines the operation that will be done
            detect: determines the fade length set to the sequence
            set: sets a desired fade length to the sequence
            clear: removes all fades from the sequence
        direction: String, determines if the function works with fadein or fadeout
            in: fadein is operated on
            out: fadeout is operated on
        fade_length: Integer, optional value used only when setting fade lengths
        fade_low_point_frame: Integer, optional value used for detecting a fade at a point other than at the edge of the sequence"""

    scene = bpy.context.scene

    #These functions check for the needed variables and create them if in set mode.  Otherwise, ends the function.
    if scene.animation_data is None:
        #No animation data in scene, create it
        if mode == 'set':
            scene.animation_data_create()
        else:
            return 0
    if scene.animation_data.action is None:
        #No action in scene, create it
        if mode == 'set':
            action = bpy.data.actions.new(scene.name+"Action")
            scene.animation_data.action = action
        else:
            return 0

    all_curves = scene.animation_data.action.fcurves
    fade_curve = False  #curve for the fades
    fade_low_point = False  #keyframe that the fade reaches minimum value at
    fade_high_point = False  #keyframe that the fade starts maximum value at
    if direction == 'in':
        if not fade_low_point_frame:
            fade_low_point_frame = sequence.frame_final_start
    else:
        if not fade_low_point_frame:
            fade_low_point_frame = sequence.frame_final_end
        fade_length = -fade_length
    fade_high_point_frame = fade_low_point_frame + fade_length

    #set up the data value to fade
    if sequence.type == 'SOUND':
        fade_variable = 'volume'
    else:
        fade_variable = 'blend_alpha'

    #attempts to find the fade keyframes by iterating through all curves in scene
    for curve in all_curves:
        if curve.data_path == 'sequence_editor.sequences_all["'+sequence.name+'"].'+fade_variable:
            #keyframes found
            fade_curve = curve

            #delete keyframes and end function
            if mode == 'clear':
                all_curves.remove(fade_curve)
                return 0

    if not fade_curve:
        #no fade animation curve found, create and continue if instructed to, otherwise end function
        if mode == 'set':
            fade_curve = all_curves.new(data_path=sequence.path_from_id(fade_variable))
        else:
            return 0

    #Detect fades or add if set mode
    fade_keyframes = fade_curve.keyframe_points
    if len(fade_keyframes) == 0:
        #no keyframes found, create them if instructed to do so
        if mode == 'set':
            fade_max_value = getattr(sequence, fade_variable)
            set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value)
        else:
            return 0

    elif len(fade_keyframes) == 1:
        #only one keyframe, use y value of keyframe as the max value for a new fade
        if mode == 'set':
            #determine fade_max_value from value at one keyframe
            fade_max_value = fade_keyframes[0].co[1]
            if fade_max_value == 0:
                fade_max_value = 1

            #remove lone keyframe, then add new fade
            fade_keyframes.remove(fade_keyframes[0])
            set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value)
        else:
            return 0

    elif len(fade_keyframes) > 1:
        #at least 2 keyframes, there may be a fade already
        if direction == 'in':
            fade_low_point = fade_keyframes[0]
            fade_high_point = fade_keyframes[1]
        elif direction == 'out':
            fade_low_point = fade_keyframes[-1]
            fade_high_point = fade_keyframes[-2]

        #check to see if the fade points are valid
        if fade_low_point.co[1] == 0:
            #opacity is 0, assume there is a fade
            if fade_low_point.co[0] == fade_low_point_frame:
                #fade low point is in the correct location
                if fade_high_point.co[1] > fade_low_point.co[1]:
                    #both fade points are valid
                    if mode == 'set':
                        fade_max_value = fade_high_point.co[1]
                        set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point, fade_high_point=fade_high_point)
                        return fade_length
                    else:
                        #fade detected!
                        return abs(fade_high_point.co[0] - fade_low_point.co[0])
                else:
                    #fade high point is not valid, low point is tho
                    if mode == 'set':
                        fade_max_value = fade_curve.evaluate(fade_high_point_frame)
                        set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point)
                        return fade_length
                    else:
                        return 0
            else:
                #fade low point is not in the correct location
                if mode == 'set':
                    #check fade high point
                    if fade_high_point.co[1] > fade_low_point.co[1]:
                        #fade exists, but is not set up properly
                        fade_max_value = fade_high_point.co[1]
                        set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point, fade_high_point=fade_high_point)
                        return fade_length
                    else:
                        #no valid fade high point
                        fade_max_value = fade_curve.evaluate(fade_high_point_frame)
                        set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point)
                        return fade_length
                else:
                    return 0

        else:
            #no valid fade detected, other keyframes are on the curve tho
            if mode == 'set':
                fade_max_value = fade_curve.evaluate(fade_high_point_frame)
                set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value)
                return fade_length
            else:
                return 0


def set_fade(fade_keyframes, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=None, fade_high_point=None):
    """Create or change a fadein or fadeout on  a set of keyframes
    Arguments:
        fade_keyframes: keyframe curve to operate on
        direction: String, determines if a fadein or fadeout will be set
            'in': Set a fadein
            'out': Set a fadeout
        fade_low_point_frame: Integer, the frame at which the fade should be at its lowest value
        fade_high_point_frame: Integer, the frame at which the fade should be at its highest value
        fade_max_value: Float, the y value for the high point of the fade
        fade_low_point: Optional, a keyframe point for the low point of the fade curve that should be moved, instead of creating a new one
        fade_high_point: Optional, a keyframe point for the high point of the fade curve that should be moved, instead of creating a new one"""

    #check if any keyframe points other than the fade high and low points are in the fade area, delete them if needed
    for keyframe in fade_keyframes:
        if direction == 'in':
            if (keyframe.co[0] < fade_high_point_frame) and (keyframe.co[0] > fade_low_point_frame):
                if (keyframe != fade_low_point) and (keyframe != fade_high_point):
                    fade_keyframes.remove(keyframe)
        if direction == 'out':
            if (keyframe.co[0] > fade_high_point_frame) and (keyframe.co[0] < fade_low_point_frame):
                if (keyframe != fade_low_point) and (keyframe != fade_high_point):
                    fade_keyframes.remove(keyframe)

    fade_length = abs(fade_high_point_frame - fade_low_point_frame)
    handle_offset = fade_length * .38
    if fade_high_point:
        #move fade high point to where it should be
        fade_high_point.co = (fade_high_point_frame, fade_max_value)
        fade_high_point.handle_left = (fade_high_point_frame - handle_offset, fade_max_value)
        fade_high_point.handle_right = (fade_high_point_frame + handle_offset, fade_max_value)
    else:
        #create new fade high point
        fade_keyframes.insert(frame=fade_high_point_frame, value=fade_max_value)
    if fade_low_point:
        if fade_length != 0:
            #move fade low point to where it should be
            fade_low_point.co = (fade_low_point_frame, 0)
            fade_low_point.handle_left = (fade_low_point_frame - handle_offset, 0)
            fade_low_point.handle_right = (fade_low_point_frame + handle_offset, 0)
        else:
            #remove fade low point
            fade_keyframes.remove(fade_low_point)
    else:
        if fade_high_point_frame != fade_low_point_frame:
            #create new fade low point
            fade_keyframes.insert(frame=fade_low_point_frame, value=0)


class VSEQFQuickFadesPanel(bpy.types.Panel):
    """Panel for QuickFades operators and properties.  Placed in the VSE properties area."""
    bl_label = "Quick Fades"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        try:
            #Check for an active sequence to operate on
            sequence = current_active(context)
            if sequence:
                return prefs.fades
            else:
                return False

        except:
            return False

    def draw(self, context):
        #Set up basic variables needed by panel
        scene = bpy.context.scene
        vseqf = scene.vseqf
        active_sequence = current_active(context)
        fadein = fades(sequence=active_sequence, mode='detect', direction='in')
        fadeout = fades(sequence=active_sequence, mode='detect', direction='out')

        layout = self.layout

        #First row, detected fades
        row = layout.row()
        if fadein > 0:
            row.label("Fadein: "+str(round(fadein))+" Frames")
        else:
            row.label("No Fadein Detected")
        if fadeout > 0:
            row.label("Fadeout: "+str(round(fadeout))+" Frames")
        else:
            row.label("No Fadeout Detected")

        #Setting fades section
        row = layout.row()
        row.prop(vseqf, 'fade')
        row = layout.row(align=True)
        row.operator('vseqf.quickfades_set', text='Set Fadein', icon='BACK').type = 'in'
        row.operator('vseqf.quickfades_set', text='Set In/Out').type = 'both'
        row.operator('vseqf.quickfades_set', text='Set Fadeout', icon='FORWARD').type = 'out'
        row = layout.row()
        row.operator('vseqf.quickfades_clear', text='Clear Fades').direction = 'both'
        row = layout.row()
        row.separator()

        #Crossfades section
        row = layout.row()
        row.prop(vseqf, 'transition')
        row = layout.row(align=True)
        row.operator('vseqf.quickfades_cross', text='Crossfade Prev Clip', icon='BACK').type = 'previous'
        row.operator('vseqf.quickfades_cross', text='Crossfade Next Clip', icon='FORWARD').type = 'next'
        row = layout.row(align=True)
        row.operator('vseqf.quickfades_cross', text='Smart Cross to Prev', icon='BACK').type = 'previoussmart'
        row.operator('vseqf.quickfades_cross', text='Smart Cross to Next', icon='FORWARD').type = 'nextsmart'


class VSEQFQuickFadesMenu(bpy.types.Menu):
    """Pop-up menu for QuickFade operators"""
    bl_idname = "vseqf.quickfades_menu"
    bl_label = "Quick Fades"

    @classmethod
    def poll(cls, context):
        del context
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        return prefs.fades

    def draw(self, context):
        scene = context.scene
        sequences = current_selected(context)
        sequence = current_active(context)

        layout = self.layout
        if sequence and len(sequences) > 0:
            #If a sequence is active
            vseqf = scene.vseqf
            fadein = fades(sequence=sequence, mode='detect', direction='in')
            fadeout = fades(sequence=sequence, mode='detect', direction='out')

            #Detected fades section
            if fadein > 0:
                layout.label("Fadein: "+str(round(fadein))+" Frames")
            else:
                layout.label("No Fadein Detected")
            if fadeout > 0:
                layout.label("Fadeout: "+str(round(fadeout))+" Frames")
            else:
                layout.label("No Fadeout Detected")

            #Fade length
            layout.prop(vseqf, 'fade')
            layout.operator('vseqf.quickfades_set', text='Set Fadein').type = 'in'
            layout.operator('vseqf.quickfades_set', text='Set Fadeout').type = 'out'
            layout.operator('vseqf.quickfades_clear', text='Clear Fades').direction = 'both'

            #Add crossfades
            layout.separator()
            layout.prop(vseqf, 'transition', text='')
            layout.operator('vseqf.quickfades_cross', text='Crossfade Prev Sequence').type = 'previous'
            layout.operator('vseqf.quickfades_cross', text='Crossfade Next Sequence').type = 'next'
            layout.operator('vseqf.quickfades_cross', text='Smart Cross to Prev').type = 'previoussmart'
            layout.operator('vseqf.quickfades_cross', text='Smart Cross to Next').type = 'nextsmart'

        else:
            layout.label("No Sequence Selected")


class VSEQFQuickFadesSet(bpy.types.Operator):
    """Operator to add fades to selected sequences
    Uses the vseqf fade_length variable for length
    Argument:
        type: String, determines if a fadein or fadeout should be set
            'in': sets a fadein
            'out': sets a fadeout
            'both': sets fadein and fadeout"""

    bl_idname = 'vseqf.quickfades_set'
    bl_label = 'VSEQF Quick Fades Set Fade'
    bl_description = 'Adds or changes fade for selected sequences'

    #Should be set to 'in' or 'out'
    type = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        #iterate through selected sequences and apply fades to them
        selected_sequences = current_selected(context)
        for sequence in selected_sequences:
            if self.type == 'both':
                fades(sequence=sequence, mode='set', direction='in', fade_length=context.scene.vseqf.fade)
                fades(sequence=sequence, mode='set', direction='out', fade_length=context.scene.vseqf.fade)
            else:
                fades(sequence=sequence, mode='set', direction=self.type, fade_length=context.scene.vseqf.fade)

        redraw_sequencers()
        return{'FINISHED'}


class VSEQFQuickFadesClear(bpy.types.Operator):
    """Operator to clear fades on selected sequences"""
    bl_idname = 'vseqf.quickfades_clear'
    bl_label = 'VSEQF Quick Fades Clear Fades'
    bl_description = 'Clears fade in and out for selected sequences'

    direction = bpy.props.StringProperty('both')
    active_only = bpy.props.BoolProperty(False)

    def execute(self, context):
        bpy.ops.ed.undo_push()
        if self.active_only:
            if self.direction != 'both':
                fades(sequence=current_active(context), mode='set', direction=self.direction, fade_length=0)
            else:
                fades(sequence=current_active(context), mode='clear', direction=self.direction, fade_length=context.scene.vseqf.fade)
        else:
            selected_sequences = current_selected(context)
            for sequence in selected_sequences:
                #iterate through selected sequences, remove fades, and set opacity to full
                if self.direction != 'both':
                    fades(sequence=sequence, mode='set', direction=self.direction, fade_length=0)
                else:
                    fades(sequence=sequence, mode='clear', direction=self.direction, fade_length=context.scene.vseqf.fade)
                sequence.blend_alpha = 1

        redraw_sequencers()
        self.direction = 'both'
        self.active_only = False
        return{'FINISHED'}


class VSEQFQuickFadesCross(bpy.types.Operator):
    """Operator to add crossfades from selected sequences
    This operator will maintain selected and active sequences

    Argument:
        type: String, determines how a fade should be added
            'next': detects the next sequence and adds a simple fade
            'previous': detects the previous sequence and adds a simple fade
            'nextsmart': detects the next sequence, adjusts the edges to create a fade of the length set in the vseqf variable 'fade', then adds the crossfade
            'previoussmart': same as nextsmart, but detects the previous sequence"""

    bl_idname = 'vseqf.quickfades_cross'
    bl_label = 'VSEQF Quick Fades Add Crossfade'
    bl_description = 'Adds a crossfade between selected sequence and next or previous sequence in timeline'

    type = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        sequences = current_sequences(context)

        #store a list of selected sequences since adding a crossfade destroys the selection
        selected_sequences = current_selected(context)
        active_sequence = current_active(context)

        for sequence in selected_sequences:
            if sequence.type != 'SOUND' and not hasattr(sequence, 'input_1'):
                first_sequence = None
                second_sequence = None
                #iterate through selected sequences and add crossfades to previous or next sequence
                if self.type == 'nextsmart':
                    #Need to find next sequence
                    first_sequence = sequence
                    second_sequence = find_close_sequence(sequences, first_sequence, 'next', mode='all')
                elif self.type == 'previoussmart':
                    #Need to find previous sequence
                    second_sequence = sequence
                    first_sequence = find_close_sequence(sequences, second_sequence, 'previous', mode='all')
                elif self.type == 'next':
                    #Need to find next sequence
                    first_sequence = sequence
                    second_sequence = find_close_sequence(sequences, first_sequence, 'next', mode='all')
                elif self.type == 'previous':
                    #Need to find previous sequence
                    second_sequence = sequence
                    first_sequence = find_close_sequence(sequences, second_sequence, 'previous', mode='all')
                if (second_sequence is not None) & (first_sequence is not None):
                    if 'smart' in self.type:
                        #adjust start and end frames of sequences based on frame_offset_end/start to overlap by amount of crossfade
                        target_fade = bpy.context.scene.vseqf.fade
                        current_fade = first_sequence.frame_final_end - second_sequence.frame_final_start
                        #if current_fade is negative, there is open space between clips, if positive, clips are overlapping
                        if current_fade <= 0:
                            fade_offset = abs(current_fade + target_fade)
                            first_sequence_offset = -round((fade_offset/2)+.1)
                            second_sequence_offset = -round((fade_offset/2)-.1)
                        else:
                            fade_offset = abs(current_fade - target_fade)
                            first_sequence_offset = round((fade_offset/2)+.1)
                            second_sequence_offset = round((fade_offset/2)-.1)

                        if abs(current_fade) < target_fade:
                            #detected overlap is not enough, extend the ends of the sequences to match the target overlap

                            if ((first_sequence.frame_offset_end > first_sequence_offset) & (second_sequence.frame_offset_start > second_sequence_offset)) | ((first_sequence.frame_offset_end == 0) & (first_sequence.frame_offset_start == 0)):
                                #both sequence offsets are larger than both target offsets or neither sequence has offsets
                                first_sequence.frame_final_end = first_sequence.frame_final_end + first_sequence_offset
                                second_sequence.frame_final_start = second_sequence.frame_final_start - second_sequence_offset

                            else:
                                #sequence offsets need to be adjusted individually
                                current_offset = first_sequence.frame_offset_end + second_sequence.frame_offset_start
                                first_sequence_offset_percent = first_sequence.frame_offset_end / current_offset
                                second_sequence_offset_percent = second_sequence.frame_offset_start / current_offset
                                first_sequence.frame_final_end = first_sequence.frame_final_end + (round(first_sequence_offset_percent * fade_offset))
                                second_sequence.frame_final_start = second_sequence.frame_final_start - (round(second_sequence_offset_percent * fade_offset))

                        elif abs(current_fade) > target_fade:
                            #detected overlap is larger than target fade, subtract equal amounts from each sequence
                            first_sequence.frame_final_end = first_sequence.frame_final_end - first_sequence_offset
                            second_sequence.frame_final_start = second_sequence.frame_final_start + second_sequence_offset
                    fade_exists = find_crossfade(sequences, first_sequence, second_sequence)
                    if not fade_exists:
                        vseqf_crossfade(first_sequence, second_sequence)

                else:
                    self.report({'WARNING'}, 'No Second Sequence Found')

        bpy.ops.sequencer.select_all(action='DESELECT')
        for sequence in selected_sequences:
            sequence.select = True
        if active_sequence:
            context.scene.sequence_editor.active_strip = active_sequence
        bpy.ops.ed.undo_push()
        return{'FINISHED'}


#Functions and classes related to QuickParents
def get_recursive(sequence, sequences):
    #recursively gathers all children of children of the given sequence
    if not sequence.lock and not hasattr(sequence, 'input_1'):
        if sequence not in sequences:
            sequences.append(sequence)
            children = find_children(sequence)
            for child in children:
                sequences = get_recursive(child, sequences)
    return sequences


def add_children(parent_sequence, child_sequences):
    """Adds parent-child relationships to sequences
    Arguments:
        parent_sequence: VSE Sequence to set as the parent
        child_sequences: List of VSE Sequence objects to set as children"""

    for child_sequence in child_sequences:
        if child_sequence.name != parent_sequence.name:
            child_sequence.parent = parent_sequence.name


def find_children(parent_sequence, name=False, sequences=False):
    """Gets a list of sequences that are children of a sequence
    Arguments:
        parent_sequence: VSE Sequence object or String name of a sequence to search for children of
        name: Boolean, if True, the passed-in 'parent_sequence' is a name of the parent, if False, the passed in 'parent_sequence' is the actual sequence object
        sequences: Optional, a list of sequences may be passed in here, they will be the only ones searched

    Returns: List of VSE Sequence objects, or empty list if none found"""

    if name:
        parent_name = parent_sequence
    else:
        parent_name = parent_sequence.name
    if not sequences:
        sequences = current_sequences(bpy.context)
        #sequences = bpy.context.scene.sequence_editor.sequences_all
    child_sequences = []
    for sequence in sequences:
        if sequence.parent == parent_name:
            child_sequences.append(sequence)
    return child_sequences


def find_parent(child_sequence):
    """Gets the parent sequence of a child sequence
    Argument:
        child_sequence: VSE Sequence object to search for the parent of
    
    Returns: VSE Sequence object if match found, Boolean False if no match found"""
    sequences = current_sequences(bpy.context)
    #sequences = bpy.context.scene.sequence_editor.sequences_all
    for sequence in sequences:
        if sequence.name == child_sequence.parent:
            return sequence
    else:
        return False


def clear_children(parent_sequence):
    """Removes all child relationships from a parent sequence
    Argument:
        parent_sequence: VSE Sequence object to search for children of"""
    scene = bpy.context.scene
    sequences = scene.sequence_editor.sequences_all
    for sequence in sequences:
        if sequence.parent == parent_sequence.name:
            clear_parent(sequence)


def clear_parent(child_sequence):
    """Removes the parent relationship of a child sequence
    Argument:
        child_sequence: VSE Sequence object to remove the parent relationship of"""
    child_sequence.parent = ''


def select_children(parent_sequence, sequences=False):
    """Selects all children of a given sequence
    Arguments:
        parent_sequence: VSE Sequence to search for children of
        sequences: Optional, list of sequences to search through"""

    children = find_children(parent_sequence, sequences=sequences)
    for child in children:
        child.select = True


def select_parent(child_sequence):
    """Selects the parent of a sequence
    Argument:
        child_sequence: VSE Sequence object to find the parent of"""

    parent = find_parent(child_sequence)
    if parent:
        parent.select = True


class VSEQFMeta(bpy.types.Operator):
    """Creates meta strip while adding children"""

    bl_idname = 'vseqf.meta_make'
    bl_label = 'Make Meta Strip'

    def execute(self, context):
        bpy.ops.ed.undo_push()
        parenting = vseqf_parenting()
        if parenting:
            selected = current_selected(context)
            for sequence in selected:
                children = find_children(sequence)
                for child in children:
                    child.select = True
        selected = current_selected(context)
        sequences = current_sequences(context)
        for sequence in sequences:
            if hasattr(sequence, 'input_1'):
                if sequence.input_1 in selected:
                    sequence.select = True
        try:
            bpy.ops.sequencer.meta_make()
        except RuntimeError:
            self.report({'ERROR'}, "Please select all related strips")
        return {'FINISHED'}


class VSEQFQuickParentsMenu(bpy.types.Menu):
    """Pop-up menu for QuickParents, displays parenting operators, and relationships"""
    bl_idname = "vseqf.quickparents_menu"
    bl_label = "Quick Parents"

    @classmethod
    def poll(cls, context):
        del context
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        return prefs.parenting

    def draw(self, context):
        sequence = current_active(context)
        layout = self.layout

        if sequence:
            sequences = current_sequences(context)

            selected = current_selected(context)
            children = find_children(sequence, sequences=sequences)
            parent = find_parent(sequence)

            layout.operator('vseqf.quickparents', text='Select Children').action = 'select_children'
            layout.operator('vseqf.quickparents', text='Select Parent').action = 'select_parent'
            if len(selected) > 1:
                #more than one sequence is selected, so children can be set
                layout.operator('vseqf.quickparents', text='Set Active As Parent').action = 'add'

            layout.operator('vseqf.quickparents', text='Clear Children').action = 'clear_children'
            layout.operator('vseqf.quickparents', text='Clear Parent').action = 'clear_parent'

            if parent:
                #Parent sequence is found, display it
                layout.separator()
                layout.label("     Parent: ")
                layout.label(parent.name)
                layout.separator()

            if len(children) > 0:
                #At least one child sequence is found, display them
                layout.separator()
                layout.label("     Children:")
                index = 0
                while index < len(children):
                    layout.label(children[index].name)
                    index = index + 1
                layout.separator()

        else:
            layout.label('No Sequence Selected')


class VSEQFQuickParents(bpy.types.Operator):
    """Changes parenting relationships on selected sequences

    Argument:
        action: String, determines what this operator will attempt to do
            'add': Adds selected sequences as children of the active sequence
            'select_children': Selects children of all selected sequences
            'select_parent': Selects parents of all selected sequences
            'clear_parent': Clears parent relationships of all selected sequences
            'clear_children': Clears all child relationships of all selected sequences"""

    bl_idname = 'vseqf.quickparents'
    bl_label = 'VSEQF Quick Parents'
    bl_description = 'Sets Or Removes Strip Parents'

    action = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        selected = current_selected(context)
        active = current_active(context)
        if not active:
            return {'CANCELLED'}

        if (self.action == 'add') and (len(selected) > 1):
            add_children(active, selected)
        else:
            if not selected:
                selected = [active]
            sequences = current_sequences(context)
            for sequence in selected:
                if self.action == 'select_children':
                    select_children(sequence, sequences=sequences)
                if self.action == 'select_parent':
                    select_parent(sequence)
                if self.action == 'clear_parent':
                    clear_parent(sequence)
                if self.action == 'clear_children':
                    clear_children(sequence)
        redraw_sequencers()
        return {'FINISHED'}


class VSEQFQuickParentsClear(bpy.types.Operator):
    """Clears the parent of a sequence
    Argument:
        strip: String, the name of the sequence to clear the parent of"""

    bl_idname = 'vseqf.quickparents_clear_parent'
    bl_label = 'VSEQF Quick Parent Remove Parent'
    bl_description = 'Removes Strip Parent'

    strip = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        sequences = current_sequences(context)
        for sequence in sequences:
            if sequence.name == self.strip:
                clear_parent(sequence)
                break
        redraw_sequencers()
        return {'FINISHED'}


class VSEQFImport(bpy.types.Operator, ImportHelper):
    """Loads different types of files into the sequencer"""
    bl_idname = 'vseqf.import'
    bl_label = 'Import Strip'

    type = bpy.props.EnumProperty(
        name="Import Type",
        items=(('MOVIE', 'Movie', ""), ("IMAGE", "Image", "")),
        default='MOVIE')

    files = bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)

    relative_path = bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True)
    start_frame = bpy.props.IntProperty(
        name="Start Frame",
        description="Start frame of the sequence strip",
        default=0)
    channel = bpy.props.IntProperty(
        name="Channel",
        description="Channel to place this strip into",
        default=1)
    replace_selection = bpy.props.BoolProperty(
        name="Replace Selection",
        description="Replace the current selection",
        default=True)
    sound = bpy.props.BoolProperty(
        name="Sound",
        description="Load sound with the movie",
        default=True)
    use_movie_framerate = bpy.props.BoolProperty(
        name="Use Movie Framerate",
        description="Use framerate from the movie to keep sound and video in sync",
        default=False)
    import_location = bpy.props.EnumProperty(
        name="Import At",
        description="Location to import strips at",
        items=(("IMPORT_FRAME", "Import At Frame", ""), ("INSERT_FRAME", "Insert At Frame", ""), ("CUT_INSERT", "Cut And Insert At Frame", ""), ("END", "Import At End", "")),
        default="IMPORT_FRAME")
    autoparent = bpy.props.BoolProperty(
        name="Auto-Parent A/V",
        description="Automatically parent audio strips to their movie strips",
        default=True)
    autoproxy = bpy.props.BoolProperty(
        name="Auto-Set Proxy",
        description="Automatically enable proxy settings",
        default=False)
    autogenerateproxy = bpy.props.BoolProperty(
        name="Auto-Generate Proxy",
        description="Automatically generate proxies for imported strips",
        default=False)
    use_placeholders = bpy.props.BoolProperty(
        name="Use Placeholders",
        description="Use placeholders for missing frames of the strip",
        default=False)
    length = bpy.props.IntProperty(
        name="Image Length",
        description="Length in frames to use for a single imported image",
        default=30)

    def draw(self, context):
        prefs = get_prefs()
        context.space_data.params.use_filter = True
        context.space_data.params.use_filter_folder = True
        if self.type == 'MOVIE':
            context.space_data.params.use_filter_movie = True
            layout = self.layout
            layout.prop(self, 'relative_path')
            layout.prop(self, 'start_frame')
            layout.prop(self, 'channel')
            layout.prop(self, 'import_location')
            layout.prop(self, 'replace_selection')
            layout.prop(self, 'sound')
            layout.prop(self, 'use_movie_framerate')
            if vseqf_parenting():
                layout.prop(self, 'autoparent')
            if prefs.proxy:
                layout.prop(self, 'autoproxy')
                layout.prop(self, 'autogenerateproxy')
        elif self.type == 'IMAGE':
            context.space_data.params.use_filter_image = True
            layout = self.layout
            number_of_files = len(self.files)
            row = layout.row()
            row.prop(self, 'relative_path')
            row = layout.row()
            row.prop(self, 'start_frame')
            row = layout.row()
            if number_of_files > 1:
                row.label("Length: "+str(number_of_files))
            else:
                row.prop(self, 'length')
            row = layout.row()
            row.prop(self, 'channel')
            row = layout.row()
            row.prop(self, 'import_location')
            row = layout.row()
            row.prop(self, 'replace_selection')
            if prefs.proxy:
                layout.prop(self, 'autoproxy')
                layout.prop(self, 'autogenerateproxy')

    def invoke(self, context, event):
        del event
        sequencer = context.scene.sequence_editor
        if not sequencer:
            context.scene.sequence_editor_create()
        if self.type == 'MOVIE':
            self.bl_label = 'Add Movie Strip'
        elif self.type == 'IMAGE':
            self.bl_label = 'Add Image'
        vseqf = context.scene.vseqf
        prefs = get_prefs()
        fps = context.scene.render.fps / context.scene.render.fps_base
        self.length = fps * 4
        self.start_frame = context.scene.frame_current
        if len(context.scene.sequence_editor.sequences_all) == 0:
            self.use_movie_framerate = True
        if prefs.parenting and vseqf.children:
            self.autoparent = vseqf.autoparent
        else:
            self.autoparent = False
        if prefs.proxy:
            self.autoproxy = vseqf.enable_proxy
            self.autogenerateproxy = vseqf.build_proxy
        else:
            self.autoproxy = False
            self.autogenerateproxy = False
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def find_end_frame(self, sequences):
        frame = 1
        for sequence in sequences:
            if sequence.frame_final_end > frame:
                frame = sequence.frame_final_end
        return frame

    def setup_proxies(self, sequences):
        for sequence in sequences:
            apply_proxy_settings(sequence)

    def execute(self, context):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            context.scene.sequence_editor_create()
        bpy.ops.ed.undo_push()
        old_snap_new_end = context.scene.vseqf.snap_new_end
        context.scene.vseqf.snap_new_end = False  #disable this so the continuous function doesnt do weird stuff while importing this
        selected = current_selected(context)
        active = current_active(context)
        end_frame = self.find_end_frame(current_sequences(context))
        dirname = os.path.dirname(self.filepath)
        bpy.ops.sequencer.select_all(action='DESELECT')
        if self.import_location == 'END':
            context.scene.frame_current = end_frame
        else:
            context.scene.frame_current = self.start_frame
        if self.import_location in ['END', 'INSERT_FRAME', 'CUT_INSERT']:
            frame = end_frame
        else:
            frame = self.start_frame
        all_imported = []
        to_parent = []
        last_frame = context.scene.frame_current
        if self.type == 'MOVIE':
            for file in self.files:
                filename = os.path.join(dirname, file.name)
                bpy.ops.sequencer.movie_strip_add(filepath=filename, frame_start=frame, relative_path=self.relative_path, channel=self.channel, replace_sel=True, sound=self.sound, use_framerate=self.use_movie_framerate)
                imported = current_selected(context)
                if len(imported) > 1:
                    #this included a sound strip, maybe other types?
                    moviestrip = False
                    soundstrip = False
                    otherstrips = []
                    for seq in imported:
                        if seq.type == 'MOVIE':
                            moviestrip = seq
                        elif seq.type == 'SOUND':
                            soundstrip = seq
                        else:
                            otherstrips.append(seq)
                        if seq.frame_final_end > frame:
                            frame = seq.frame_final_end
                    if moviestrip and soundstrip:
                        to_parent.append([moviestrip, soundstrip])
                else:
                    frame = imported[0].frame_final_end
                all_imported.extend(imported)
        elif self.type == 'IMAGE':
            files = [{"name": i.name} for i in self.files]
            if len(self.files) > 1:
                length = len(self.files)
            else:
                length = self.length
            bpy.ops.sequencer.image_strip_add(directory=dirname, files=files, relative_path=self.relative_path, frame_start=frame, frame_end=frame+length-1, channel=self.channel, replace_sel=True, use_placeholders=self.use_placeholders)
            imported = current_selected(context)
            all_imported.extend(imported)
        if self.import_location == 'INSERT_FRAME' or self.import_location == 'CUT_INSERT':
            new_end_frame = self.find_end_frame(current_sequences(context))
            move_forward = new_end_frame - end_frame
            move_back = end_frame - self.start_frame + move_forward
            if self.import_location == 'INSERT_FRAME':
                cut_type = 'INSERT_ONLY'
            else:
                cut_type = 'INSERT'
            bpy.ops.vseqf.cut(type=cut_type, use_insert=True, insert=move_forward, use_all=True, all=True)
            for sequence in all_imported:
                sequence.frame_start = sequence.frame_start - move_back
        if self.sound and self.autoparent:
            #autoparent audio strips to video
            for pair in to_parent:
                movie, sound = pair
                add_children(movie, [sound])
        if self.autoproxy:
            #auto-set proxy settings
            self.setup_proxies(all_imported)
        if not self.replace_selection:
            bpy.ops.sequencer.select_all(action='DESELECT')
            for sequence in selected:
                sequence.select = True
            if active:
                context.scene.sequence_editor.active_strip = active
        else:
            bpy.ops.sequencer.select_all(action='DESELECT')
            for sequence in all_imported:
                sequence.select = True
        if self.autoproxy and self.autogenerateproxy and not context.scene.vseqf.build_proxy:
            bpy.ops.sequencer.rebuild_proxy('INVOKE_DEFAULT')
        for file in all_imported:
            if file.frame_final_end > last_frame:
                last_frame = file.frame_final_end
        if old_snap_new_end:
            context.scene.frame_current = last_frame
        context.scene.vseqf.snap_new_end = old_snap_new_end
        return {'FINISHED'}


#Classes related to QuickSnaps
class VSEQFQuickSnapsMenu(bpy.types.Menu):
    """QuickSnaps pop-up menu listing snapping operators"""
    bl_idname = "vseqf.quicksnaps_menu"
    bl_label = "Quick Snaps"

    def draw(self, context):
        layout = self.layout
        layout.operator('vseqf.quicksnaps', text='Cursor To Nearest Second').type = 'cursor_to_seconds'
        props = layout.operator("sequencer.strip_jump", text="Jump to Previous Sequence")
        props.next = False
        props.center = False
        props = layout.operator("sequencer.strip_jump", text="Jump to Next Sequence")
        props.next = True
        props.center = False
        try:
            #Display only if active sequence is set
            sequence = current_active(context)
            if sequence:
                layout.operator('vseqf.quicksnaps', text='Cursor To Beginning Of Active').type = 'cursor_to_beginning'
                layout.operator('vseqf.quicksnaps', text='Cursor To End Of Active').type = 'cursor_to_end'
                layout.separator()
                layout.operator('vseqf.quicksnaps', text='Selected To Cursor').type = 'selection_to_cursor'
                layout.separator()
                layout.operator('vseqf.quicksnaps', text='Selected Beginnings To Cursor').type = 'begin_to_cursor'
                layout.operator('vseqf.quicksnaps', text='Selected Ends To Cursor').type = 'end_to_cursor'
                layout.operator('vseqf.quicksnaps', text='Selected To Previous Sequence').type = 'sequence_to_previous'
                layout.operator('vseqf.quicksnaps', text='Selected To Next Sequence').type = 'sequence_to_next'
        except:
            pass


class VSEQFQuickSnaps(bpy.types.Operator):
    """Operator for snapping the cursor and sequences
    Argument:
        type: String, snapping operation to perform
            'cursor_to_seconds': Rounds the cursor position to the nearest second
            'cursor_to_beginning': Moves the cursor to the beginning of the active sequence
            'cursor_to_end': Moves the cursor to the end of the active sequence
            'begin_to_cursor': Moves the beginning of selected sequences to the cursor position
            'end_to_cursor': Moves the ending of selected sequences to the cursor position
            'sequence_to_previous': Snaps the active sequence to the closest previous sequence
            'sequence_to_next': Snaps the active sequence to the closest next sequence
            'selection_to_cursor': Snaps the sequence edges or sequence beginning to the cursor"""

    bl_idname = 'vseqf.quicksnaps'
    bl_label = 'VSEQF Quick Snaps'
    bl_description = 'Snaps selected sequences'

    type = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        #Set up variables needed for operator
        prefs = get_prefs()
        selected = current_selected(context)
        scene = context.scene
        active = current_active(context)
        sequences = current_sequences(context)
        frame = scene.frame_current

        #Cursor snaps
        if self.type == 'cursor_to_seconds':
            fps = scene.render.fps / scene.render.fps_base
            scene.frame_current = round(round(scene.frame_current / fps) * fps)
        elif self.type == 'cursor_to_beginning':
            if active:
                scene.frame_current = active.frame_final_start
        elif self.type == 'cursor_to_end':
            if active:
                scene.frame_current = active.frame_final_end

        #Sequence snaps
        else:
            parenting = vseqf_parenting()
            to_snap = []
            all_sequences = []
            if parenting:
                for sequence in sequences:
                    parent = find_parent(sequence)
                    if not parent or parent not in selected:
                        all_sequences.append(sequence)
                        if sequence.select:
                            to_snap.append(sequence)
            else:
                to_snap = selected
                all_sequences = sequences
            if active:
                previous = find_close_sequence(all_sequences, active, 'previous', 'any', sounds=True)
                next_seq = find_close_sequence(all_sequences, active, 'next', 'any', sounds=True)
            else:
                previous = None
                next_seq = None
            to_check = []
            for sequence in to_snap:
                if not hasattr(sequence, 'input_1'):
                    moved = 0
                    to_check.append([sequence, sequence.frame_start, sequence.frame_final_start, sequence.frame_final_end])
                    if self.type == 'selection_to_cursor':
                        children = find_children(sequence)
                        original_left = sequence.frame_final_start
                        original_right = sequence.frame_final_end
                        if sequence.select_left_handle and sequence.select_right_handle:
                            #both handles selected, only snap one
                            #if the cursor is on one side, snap that handle.  if the cursor is in the middle, snap closest
                            if frame < sequence.frame_final_start:
                                sequence.frame_final_start = frame
                            elif frame > sequence.frame_final_end:
                                sequence.frame_final_end = frame
                            elif frame > sequence.frame_final_start and frame < sequence.frame_final_end:
                                #cursor is in the middle of the sequence
                                start_distance = frame - sequence.frame_final_start
                                end_distance = sequence.frame_final_end - frame
                                if end_distance < start_distance:
                                    sequence.frame_final_end = frame
                                else:
                                    sequence.frame_final_start = frame
                        elif sequence.select_left_handle:
                            if frame >= sequence.frame_final_end:
                                self.type = 'end_to_cursor'
                            else:
                                sequence.frame_final_start = frame
                        elif sequence.select_right_handle:
                            if frame <= sequence.frame_final_start:
                                self.type = 'begin_to_cursor'
                            else:
                                sequence.frame_final_end = frame
                        else:
                            self.type = 'begin_to_cursor'
                        if self.type != 'begin_to_cursor':
                            #fix child edges
                            if parenting:
                                for child in children:
                                    if child.frame_final_start == original_left:
                                        to_check.append([child, child.frame_start, child.frame_final_start, child.frame_final_end])
                                        child.frame_final_start = sequence.frame_final_start
                                    if child.frame_final_end == original_right:
                                        to_check.append([child, child.frame_start, child.frame_final_start, child.frame_final_end])
                                        child.frame_final_end = sequence.frame_final_end

                    if self.type == 'begin_to_cursor':
                        offset = sequence.frame_final_start - sequence.frame_start
                        new_start = (frame - offset)
                        moved = new_start - sequence.frame_start
                        sequence.frame_start = new_start
                    if self.type == 'end_to_cursor':
                        offset = sequence.frame_final_start - sequence.frame_start
                        new_start = (frame - offset - sequence.frame_final_duration)
                        moved = new_start - sequence.frame_start
                        sequence.frame_start = new_start
                    if self.type == 'sequence_to_previous':
                        if previous:
                            offset = sequence.frame_final_start - sequence.frame_start
                            new_start = (previous.frame_final_end - offset)
                            moved = new_start - sequence.frame_start
                            sequence.frame_start = new_start
                        else:
                            self.report({'WARNING'}, 'No Previous Sequence Found')
                    if self.type == 'sequence_to_next':
                        if next_seq:
                            offset = sequence.frame_final_start - sequence.frame_start
                            new_start = (next_seq.frame_final_start - offset - sequence.frame_final_duration)
                            moved = new_start - sequence.frame_start
                            sequence.frame_start = new_start
                        else:
                            self.report({'WARNING'}, 'No Next Sequence Found')
                    if moved != 0:
                        if parenting:
                            children = get_recursive(sequence, [])
                            for child in children:
                                if child != sequence:
                                    child.frame_start = child.frame_start + moved
            #fix fades
            if prefs.fades:
                for check in to_check:
                    sequence, old_pos, old_start, old_end = check
                    if old_pos == sequence.frame_start:
                        if old_start != sequence.frame_final_start:
                            # fix fade in
                            fade_in = fades(sequence, mode='detect', direction='in', fade_low_point_frame=old_start)
                            if fade_in > 0:
                                fades(sequence, mode='set', direction='in', fade_length=fade_in)
                        if old_end != sequence.frame_final_end:
                            # fix fade out
                            fade_out = fades(sequence, mode='detect', direction='out', fade_low_point_frame=old_end)
                            if fade_out > 0:
                                fades(sequence, mode='set', direction='out', fade_length=fade_out)
        return{'FINISHED'}


#Functions and classes related to QuickList
def quicklist_sorted_strips(sequences=None, sortmode=None):
    """Gets a list of current VSE Sequences sorted by the vseqf 'quicklist_sort' mode
    Arguments:
        sequences: Optional, list of sequences to sort
        sortmode: Optional, overrides the sort method, can be set to any of the sort methods in the vseqf setting 'quicklist_sort'

    Returns: List of VSE Sequence objects"""

    if not sequences:
        sequences = current_sequences(bpy.context)
    if not sortmode:
        sortmode = bpy.context.scene.vseqf.quicklist_sort
    reverse = bpy.context.scene.vseqf.quicklist_sort_reverse

    #sort the sequences
    if sortmode == 'TITLE':
        sequences.sort(key=lambda seq: seq.name)
        if sequences and reverse:
            sequences.reverse()
    elif sortmode == 'LENGTH':
        sequences.sort(key=lambda seq: seq.frame_final_duration)
        if sequences and not reverse:
            sequences.reverse()
    else:
        sequences.sort(key=lambda seq: seq.frame_final_start)
        if sequences and reverse:
            sequences.reverse()

    #Check for effect sequences and move them next to their parent sequence
    for sequence in sequences:
        if hasattr(sequence, 'input_1'):
            resort = sequences.pop(sequences.index(sequence))
            parentindex = sequences.index(sequence.input_1)
            sequences.insert(parentindex + 1, resort)

    return sequences


def swap_sequence(first, second):
    """Swaps two sequences in the VSE, attempts to maintain channels.
    Arguments:
        first: First sequence, must be the one to the left
        second: Second sequence, must be the one to the right"""

    end_frame = find_sequences_end(current_sequences(bpy.context))
    first_forward_offset = end_frame - first.frame_final_start
    first_offset = second.frame_final_duration
    new_first_final_start = first.frame_final_start + first_offset
    new_first_final_end = first.frame_final_end + first_offset
    new_first_start_forward = first.frame_start + first_forward_offset
    new_first_start = first.frame_start + first_offset
    first_channel_offset = second.channel - first.channel
    new_first_channel = first.channel + first_channel_offset
    while sequencer_area_filled(new_first_final_start, new_first_final_end, new_first_channel, new_first_channel, [second, first]):
        new_first_channel = new_first_channel + 1

    second_offset = first.frame_final_start - second.frame_final_start
    new_second_final_start = second.frame_final_start + second_offset
    new_second_final_end = second.frame_final_end + second_offset
    new_second_start = second.frame_start + second_offset
    second_channel_offset = first.channel - second.channel
    new_second_channel = second.channel + second_channel_offset
    while sequencer_area_filled(new_second_final_start, new_second_final_end, new_second_channel, new_second_channel, [first, second]):
        new_second_channel = new_second_channel + 1

    first.frame_start = new_first_start_forward
    first.channel = new_first_channel
    second.frame_start = new_second_start
    second.channel = new_second_channel
    first.frame_start = new_first_start
    to_check = []
    if vseqf_parenting():
        first_children = get_recursive(first, [])
        second_children = get_recursive(second, [])
        for child in first_children:
            if child != first:
                new_start = child.frame_final_start + first_offset
                new_pos = child.frame_start + first_offset
                new_end = child.frame_final_end + first_offset
                new_channel = child.channel + first_channel_offset
                to_check.append([child, new_channel])
                while sequencer_area_filled(new_start, new_end, new_channel, new_channel, [child]):
                    new_channel = new_channel + 1
                child.frame_start = new_pos
                child.channel = new_channel
                child.frame_start = new_pos
        for child in second_children:
            if child != second:
                new_start = child.frame_final_start + second_offset
                new_pos = child.frame_start + second_offset
                new_end = child.frame_final_end + second_offset
                new_channel = child.channel + second_channel_offset
                to_check.append([child, new_channel])
                while sequencer_area_filled(new_start, new_end, new_channel, new_channel, [child]):
                    new_channel = new_channel + 1
                child.frame_start = new_pos
                child.channel = new_channel
                child.frame_start = new_pos
        for check in to_check:
            child, channel = check
            if not sequencer_area_filled(child.frame_final_start, child.frame_final_end, channel, channel, []):
                child.channel = channel


class VSEQFQuickListPanel(bpy.types.Panel):
    """Panel for displaying QuickList"""
    bl_label = "Quick List"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Quick List"

    @classmethod
    def poll(cls, context):
        del context
        #Check if panel is disabled
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for sequences
        if not bpy.context.sequences:
            return False
        if len(bpy.context.sequences) > 0:
            return prefs.list
        else:
            return False

    def draw(self, context):
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        scene = bpy.context.scene
        sequences = current_sequences(context)
        active = current_active(context)
        vseqf = scene.vseqf

        #Sort the sequences
        sorted_sequences = quicklist_sorted_strips()

        layout = self.layout

        #Display Mode
        row = layout.row(align=True)
        row.label('Display:')
        row.prop(vseqf, 'quicklist_editing', toggle=True)
        if prefs.parenting:
            row.prop(vseqf, 'quicklist_parenting', toggle=True)
        if prefs.tags:
            row.prop(vseqf, 'quicklist_tags', toggle=True)

        #Select all and sort buttons
        row = layout.row()
        row.operator('vseqf.quicklist_select', text='Select/Deselect All Sequences').sequence = ''
        row = layout.row(align=True)
        row.label('Sort By:')
        row.prop(vseqf, 'quicklist_sort', expand=True)
        if vseqf.quicklist_sort_reverse:
            reverse_icon = 'TRIA_UP'
        else:
            reverse_icon = 'TRIA_DOWN'
        row.prop(vseqf, 'quicklist_sort_reverse', text='', icon=reverse_icon, toggle=True)
        box = None

        #Display all sequences
        for index, sequence in enumerate(sorted_sequences):
            if vseqf.quicklist_sort == 'POSITION':
                column = layout.split(percentage=0.93, align=True)
            else:
                column = layout
            if hasattr(sequence, 'input_1') and box is not None:
                #Effect sequence, add an indent
                row = box.row()
                row.separator()
                row.separator()
                outline = row.box()
            else:
                outline = column.box()
            box = outline.column()

            #First row - mute, lock, type and title
            if sequence == active:
                subbox = box.box()
                row = subbox.row(align=True)
            else:
                row = box.row(align=True)
            split = row.split(align=True)
            split.prop(sequence, 'mute', text='')
            split.prop(sequence, 'lock', text='')
            split = row.split(align=True, percentage=0.2)
            col = split.column(align=True)
            col.operator('vseqf.quicklist_select', text="("+sequence.type+")").sequence = sequence.name
            col.active = sequence.select
            col = split.column(align=True)
            col.prop(sequence, 'name', text='')

            #Second row - length and position in time index
            row = box.row()
            split = row.split(percentage=0.8)
            col = split.row()
            col.label("Len: "+timecode_from_frames(sequence.frame_final_duration, (scene.render.fps / scene.render.fps_base), levels=4))
            col.label("Pos: "+timecode_from_frames(sequence.frame_start, (scene.render.fps / scene.render.fps_base), levels=4))

            #Third row - length, position and proxy toggle
            if vseqf.quicklist_editing:
                subbox = box.box()
                row = subbox.row()
                split = row.split(percentage=0.8)
                col = split.row(align=True)
                col.prop(sequence, 'frame_final_duration', text="Len")
                col.prop(sequence, 'frame_start', text="Pos")
                col = split.row()
                if (sequence.type != 'SOUND') and (sequence.type != 'MOVIECLIP') and (not hasattr(sequence, 'input_1')):
                    col.prop(sequence, 'use_proxy', text='Proxy', toggle=True)
                    if sequence.use_proxy:
                        #Proxy is enabled, add row for proxy settings
                        row = subbox.row()
                        split = row.split(percentage=0.33)
                        col = split.row(align=True)
                        col.prop(sequence.proxy, 'quality')
                        col = split.row(align=True)
                        col.prop(sequence.proxy, 'build_25', toggle=True)
                        col.prop(sequence.proxy, 'build_50', toggle=True)
                        col.prop(sequence.proxy, 'build_75', toggle=True)
                        col.prop(sequence.proxy, 'build_100', toggle=True)

            #list tags if there are any
            if prefs.tags and len(sequence.tags) > 0 and vseqf.quicklist_tags:
                line = 1
                linemax = 4
                subbox = box.box()
                row = subbox.row()
                row.label('Tags:')
                for tag in sequence.tags:
                    if line > linemax:
                        row = subbox.row()
                        row.label('')
                        line = 1
                    split = row.split(percentage=.8, align=True)
                    split.operator('vseqf.quicktags_select', text=tag.text).text = tag.text
                    split.operator('vseqf.quicktags_remove_from', text='', icon='X').tag = tag.text+'\n'+sequence.name
                    line = line + 1

            #List children sequences if found
            children = find_children(sequence, sequences=sequences)
            if len(children) > 0 and vseqf.quicklist_parenting and prefs.parenting:
                subbox = box.box()
                row = subbox.row()
                split = row.split(percentage=0.25)
                col = split.column()
                col.label('Children:')
                col = split.column()
                for child in children:
                    subsplit = col.split(percentage=0.85)
                    subsplit.label(child.name)
                    subsplit.operator('vseqf.quickparents_clear_parent', text="", icon='X').strip = child.name

            #List sub-sequences in a meta sequence
            if sequence.type == 'META':
                row = box.row()
                split = row.split(percentage=0.25)
                col = split.column()
                col.label('Sub-sequences:')
                col = split.column()
                for i, subsequence in enumerate(sequence.sequences):
                    if i > 6:
                        #Stops listing sub-sequences if list is too long
                        col.label('...')
                        break
                    col.label(subsequence.name)
            if vseqf.quicklist_sort == 'POSITION' and not hasattr(sequence, 'input_1'):
                col = column.column(align=True)
                col.operator('vseqf.quicklist_up', text='', icon='TRIA_UP').sequence = sequence.name
                col.operator('vseqf.quicklist_down', text='', icon='TRIA_DOWN').sequence = sequence.name


class VSEQFQuickListUp(bpy.types.Operator):
    """Attempts to switch a sequence with the previous sequence
    If no previous sequence is found, nothing is done

    Argument:
        sequence: String, the name of the sequence to switch"""

    bl_idname = "vseqf.quicklist_up"
    bl_label = "VSEQF Quick List Move Sequence Up"
    bl_description = "Move Sequence Up One"

    sequence = bpy.props.StringProperty()

    def execute(self, context):
        sequences = current_sequences(context)
        for sequence in sequences:
            if sequence.name == self.sequence:
                switchwith = find_close_sequence(sequences=sequences, selected_sequence=sequence, direction='previous', mode='simple', sounds=True, effects=False, children=not context.scene.vseqf.children)
                if switchwith:
                    bpy.ops.ed.undo_push()
                    swap_sequence(switchwith, sequence)
                break
        return {'FINISHED'}


class VSEQFQuickListDown(bpy.types.Operator):
    """Attempts to switch a sequence with the next sequence
    If no next sequence is found, nothing is done

    Argument:
        sequence: String, the name of the sequence to switch"""

    bl_idname = "vseqf.quicklist_down"
    bl_label = "VSEQF Quick List Move Sequence Down"
    bl_description = "Move Sequence Down One"

    sequence = bpy.props.StringProperty()

    def execute(self, context):
        sequences = current_sequences(context)
        for sequence in sequences:
            if sequence.name == self.sequence:
                switchwith = find_close_sequence(sequences=sequences, selected_sequence=sequence, direction='next', mode='simple', sounds=True, effects=False, children=not context.scene.vseqf.children)
                if switchwith:
                    bpy.ops.ed.undo_push()
                    swap_sequence(sequence, switchwith)
                break
        return {'FINISHED'}


class VSEQFQuickListSelect(bpy.types.Operator):
    """Toggle-selects a sequence by its name
    Argument:
        sequence: String, name of the sequence to select.  If blank, all sequences will be toggle-selected"""

    bl_idname = "vseqf.quicklist_select"
    bl_label = "VSEQF Quick List Select Sequence"

    sequence = bpy.props.StringProperty()

    def execute(self, context):
        sequences = current_sequences(context)
        if self.sequence == '':
            bpy.ops.ed.undo_push()
            bpy.ops.sequencer.select_all(action='TOGGLE')
        else:
            for sequence in sequences:
                if sequence.name == self.sequence:
                    bpy.ops.ed.undo_push()
                    sequence.select = not sequence.select
                    break
        return {'FINISHED'}


#Functions and classes related to QuickMarkers
def draw_quickmarker_menu(self, context):
    """Draws the submenu for the QuickMarker presets, placed in the sequencer markers menu"""
    layout = self.layout
    if len(context.scene.vseqf.marker_presets) > 0:
        layout.menu('vseqf.quickmarkers_menu', text="Quick Markers")


class VSEQFQuickMarkersPanel(bpy.types.Panel):
    """Panel for QuickMarkers operators and properties"""
    bl_label = "Quick Markers"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        return prefs.markers

    def draw(self, context):
        scene = context.scene
        vseqf = scene.vseqf
        layout = self.layout

        row = layout.row()
        split = row.split(percentage=.9, align=True)
        split.prop(vseqf, 'current_marker')
        split.operator('vseqf.quickmarkers_add_preset', text="", icon="PLUS").preset = vseqf.current_marker
        row = layout.row()
        row.template_list("VSEQFQuickMarkerPresetList", "", vseqf, 'marker_presets', vseqf, 'marker_index', rows=2)
        row = layout.row()
        row.prop(vseqf, 'marker_deselect', toggle=True)
        row = layout.row()
        row.label("Marker List:")
        row = layout.row()
        row.template_list("VSEQFQuickMarkerList", "", scene, "timeline_markers", scene.vseqf, "marker_index", rows=4)


class VSEQFQuickMarkerPresetList(bpy.types.UIList):
    """Draws an editable list of QuickMarker presets"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(percentage=.9, align=True)
        split.operator('vseqf.quickmarkers_place', text=item.text).marker = item.text
        split.operator('vseqf.quickmarkers_remove_preset', text='', icon='X').marker = item.text

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, property):
        del context
        markers = getattr(data, property)
        helper = bpy.types.UI_UL_list
        flt_neworder = helper.sort_items_by_name(markers, 'text')
        return [], flt_neworder


class VSEQFQuickMarkerList(bpy.types.UIList):
    """Draws an editable list of current markers in the timeline"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del data, icon, active_data, active_propname
        timecode = timecode_from_frames(item.frame, (context.scene.render.fps / context.scene.render.fps_base), levels=0, subsecond_type='frames')
        split = layout.split(percentage=.9, align=True)
        subsplit = split.split(align=True)
        subsplit.operator('vseqf.quickmarkers_jump', text=item.name+' ('+timecode+')').frame = item.frame
        if item.frame == context.scene.frame_current:
            subsplit.enabled = False
        split.operator('vseqf.quickmarkers_delete', text='', icon='X').frame = item.frame

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, property):
        del context
        markers = getattr(data, property)
        helper = bpy.types.UI_UL_list
        flt_neworder = helper.sort_items_helper(list(enumerate(markers)), key=lambda x: x[1].frame)
        return [], flt_neworder


class VSEQFQuickMarkerDelete(bpy.types.Operator):
    """Operator to delete a marker on a given frame
    If no marker is on the frame, nothing will be done

    Argument:
        frame: Integer, the frame to delete a marker from"""

    bl_idname = 'vseqf.quickmarkers_delete'
    bl_label = 'Delete Marker At Frame'

    frame = bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        markers = scene.timeline_markers
        for marker in markers:
            if marker.frame == self.frame:
                bpy.ops.ed.undo_push()
                markers.remove(marker)
                break
        return{'FINISHED'}


class VSEQFQuickMarkerMove(bpy.types.Operator):
    bl_idname = 'vseqf.quickmarkers_move'
    bl_label = 'Move This Marker'

    frame = bpy.props.IntProperty()

    def execute(self, context):
        marker = None
        for timeline_marker in context.scene.timeline_markers:
            if timeline_marker.frame == self.frame:
                marker = timeline_marker
                timeline_marker.select = True
            else:
                timeline_marker.select = False
        if marker:
            bpy.ops.marker.move('INVOKE_DEFAULT')
        return {'FINISHED'}


class VSEQFQuickMarkerRename(bpy.types.Operator):
    bl_idname = 'vseqf.quickmarkers_rename'
    bl_label = 'Rename This Marker'

    marker_name = bpy.props.StringProperty(name='Marker Name')

    def execute(self, context):
        for marker in context.scene.timeline_markers:
            if marker.frame == context.scene.vseqf.current_marker_frame:
                marker.name = self.marker_name
        return{'FINISHED'}

    def invoke(self, context, event):
        del event
        for marker in context.scene.timeline_markers:
            if marker.frame == context.scene.vseqf.current_marker_frame:
                self.marker_name = marker.name
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class VSEQFQuickMarkerJump(bpy.types.Operator):
    """Operator to move the cursor to a given frame
    Note that a marker doesn't have to be at the frame, that is just the way the script uses this.

    Argument:
        frame: Integer, the frame number to jump to"""
    bl_idname = 'vseqf.quickmarkers_jump'
    bl_label = 'Jump To Timeline Marker'

    frame = bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        scene.frame_current = self.frame
        return{'FINISHED'}


class VSEQFQuickMarkersMenu(bpy.types.Menu):
    """Menu for adding QuickMarkers to the current frame of the timeline"""
    bl_idname = "vseqf.quickmarkers_menu"
    bl_label = "Quick Markers"

    @classmethod
    def poll(cls, context):
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()
        return prefs.markers

    def draw(self, context):
        del context
        scene = bpy.context.scene
        vseqf = scene.vseqf
        layout = self.layout
        for marker in vseqf.marker_presets:
            layout.operator('vseqf.quickmarkers_place', text=marker.text).marker = marker.text


class VSEQFQuickMarkersPlace(bpy.types.Operator):
    """Adds a marker with a specific name to the current frame of the timeline
    If a marker already exists at the current frame, it will be renamed

    Argument:
        marker: String, the name of the marker to place"""

    bl_idname = 'vseqf.quickmarkers_place'
    bl_label = 'VSEQF Quick Markers Place A Marker'

    marker = bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        vseqf = scene.vseqf
        frame = scene.frame_current
        exists = False
        for marker in scene.timeline_markers:
            if marker.frame == frame:
                bpy.ops.ed.undo_push()
                marker.name = self.marker
                if vseqf.marker_deselect:
                    marker.select = False
                exists = True
        if not exists:
            bpy.ops.ed.undo_push()
            marker = scene.timeline_markers.new(name=self.marker, frame=frame)
            if vseqf.marker_deselect:
                marker.select = False
        return{'FINISHED'}


class VSEQFQuickMarkersRemovePreset(bpy.types.Operator):
    """Removes a marker name preset from the QuickMarkers preset list

    Argument:
        marker: String, the name of the marker preset to be removed"""

    bl_idname = 'vseqf.quickmarkers_remove_preset'
    bl_label = 'VSEQF Quick Markers Remove Preset'

    #marker name to be removed
    marker = bpy.props.StringProperty()

    def execute(self, context):
        vseqf = context.scene.vseqf
        for index, marker_preset in reversed(list(enumerate(vseqf.marker_presets))):
            if marker_preset.text == self.marker:
                bpy.ops.ed.undo_push()
                vseqf.marker_presets.remove(index)
        return{'FINISHED'}


class VSEQFQuickMarkersAddPreset(bpy.types.Operator):
    """Adds a name preset to QuickMarkers presets
    If the name already exists in the presets, the operator is canceled

    Argument:
        preset: String, the name of the marker preset to add"""

    bl_idname = 'vseqf.quickmarkers_add_preset'
    bl_label = 'VSEQF Quick Markers Add Preset'

    preset = bpy.props.StringProperty()

    def execute(self, context):
        if not self.preset:
            return {'CANCELLED'}
        vseqf = context.scene.vseqf
        for marker_preset in vseqf.marker_presets:
            if marker_preset.text == self.preset:
                return {'CANCELLED'}
        bpy.ops.ed.undo_push()
        preset = vseqf.marker_presets.add()
        preset.text = self.preset
        return {'FINISHED'}


#Functions and classes related to Quick Batch Render
def batch_render_complete_handler(scene):
    """Handler called when each element of a batch render is completed"""

    scene.vseqf.batch_rendering = False
    handlers = bpy.app.handlers.render_complete
    for handler in handlers:
        if "batch_render_complete_handler" in str(handler):
            handlers.remove(handler)


def batch_render_cancel_handler(scene):
    """Handler called when the user cancels a render that is part of a batch render"""

    scene.vseqf.batch_rendering_cancel = True
    handlers = bpy.app.handlers.render_cancel
    for handler in handlers:
        if "batch_render_cancel_handler" in str(handler):
            handlers.remove(handler)


class VSEQFQuickBatchRenderPanel(bpy.types.Panel):
    """Panel for displaying QuickBatchRender settings and operators"""

    bl_label = "Quick Batch Render"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for sequences
        if not context.sequences:
            return False
        if len(context.sequences) > 0:
            return prefs.batch
        else:
            return False

    def draw(self, context):
        scene = context.scene
        vseqf = scene.vseqf

        layout = self.layout
        row = layout.row()
        row.operator('vseqf.quickbatchrender', text='Batch Render')
        row = layout.row()
        row.prop(vseqf, 'batch_render_directory')
        row = layout.row()
        row.prop(vseqf, 'batch_selected', toggle=True)
        row = layout.row()
        row.prop(vseqf, 'batch_effects', toggle=True)
        row.prop(vseqf, 'batch_audio', toggle=True)
        row = layout.row()
        row.prop(vseqf, 'batch_meta')
        box = layout.box()
        row = box.row()
        row.label("Render Presets:")
        row = box.row()
        row.prop(vseqf, 'video_settings_menu', text='Opaque Strips')
        row = box.row()
        row.prop(vseqf, 'transparent_settings_menu', text='Transparent Strips')
        row = box.row()
        row.prop(vseqf, 'audio_settings_menu', text='Audio Strips')


class VSEQFQuickBatchRender(bpy.types.Operator):
    """Modal operator that runs a batch render on all sequences in the timeline"""

    bl_idname = 'vseqf.quickbatchrender'
    bl_label = 'VSEQF Quick Batch Render'
    bl_description = 'Renders out sequences in the timeline to a folder and reimports them.'

    _timer = None

    rendering = bpy.props.BoolProperty(default=False)
    renders = []
    rendering_sequence = None
    rendering_scene = None
    original_scene = None
    file = bpy.props.StringProperty('')
    total_renders = bpy.props.IntProperty(0)
    total_frames = bpy.props.IntProperty(0)
    audio_frames = bpy.props.IntProperty(0)
    rendering_scene_name = ''

    def set_render_settings(self, scene, setting, transparent):
        """Applies a render setting preset to a given scene

        Arguments:
            scene: Scene object to apply the settings to
            setting: String, the setting preset name to apply.  Accepts values in the vseqf setting 'video_settings_menu'
            transparent: Boolean, whether this scene should be set up to render transparency or not"""

        pixels = scene.render.resolution_x * scene.render.resolution_y * (scene.render.resolution_percentage / 100)
        if setting == 'DEFAULT':
            if transparent:
                scene.render.image_settings.color_mode = 'RGBA'
            else:
                scene.render.image_settings.color_mode = 'RGB'
        elif setting == 'AVIJPEG':
            scene.render.image_settings.file_format = 'AVI_JPEG'
            scene.render.image_settings.color_mode = 'RGB'
            scene.render.image_settings.quality = 95
        elif setting == 'H264':
            #Blender 2.79 will change this setting, so this is to ensure backwards compatibility
            try:
                scene.render.image_settings.file_format = 'H264'
            except:
                scene.render.image_settings.file_format = 'FFMPEG'
            scene.render.image_settings.color_mode = 'RGB'
            scene.render.ffmpeg.format = 'MPEG4'
            kbps = int(pixels/230)
            maxkbps = kbps*1.2
            scene.render.ffmpeg.maxrate = maxkbps
            scene.render.ffmpeg.video_bitrate = kbps
            scene.render.ffmpeg.audio_codec = 'NONE'
        elif setting == 'JPEG':
            scene.render.image_settings.file_format = 'JPEG'
            scene.render.image_settings.color_mode = 'RGB'
            scene.render.image_settings.quality = 95
        elif setting == 'PNG':
            scene.render.image_settings.file_format = 'PNG'
            if transparent:
                scene.render.image_settings.color_mode = 'RGBA'
            else:
                scene.render.image_settings.color_mode = 'RGB'
            scene.render.image_settings.color_depth = '8'
            scene.render.image_settings.compression = 90
        elif setting == 'TIFF':
            scene.render.image_settings.file_format = 'TIFF'
            if transparent:
                scene.render.image_settings.color_mode = 'RGBA'
            else:
                scene.render.image_settings.color_mode = 'RGB'
            scene.render.image_settings.color_depth = '16'
            scene.render.image_settings.tiff_codec = 'DEFLATE'
        elif setting == 'EXR':
            scene.render.image_settings.file_format = 'OPEN_EXR'
            if transparent:
                scene.render.image_settings.color_mode = 'RGBA'
            else:
                scene.render.image_settings.color_mode = 'RGB'
            scene.render.image_settings.color_depth = '32'
            scene.render.image_settings.exr_codec = 'ZIP'

    def render_sequence(self, sequence):
        """Begins rendering process: creates a temporary scene, sets it up, copies the sequence to the temporary scene, and begins rendering
        Arguments:
            sequence: VSE Sequence object to begin rendering"""

        self.rendering = True
        self.rendering_sequence = sequence
        self.original_scene = bpy.context.scene
        bpy.ops.sequencer.select_all(action='DESELECT')
        sequence.select = True
        bpy.ops.sequencer.copy()

        #create a temporary scene
        bpy.ops.scene.new(type='EMPTY')
        self.rendering_scene = bpy.context.scene
        self.rendering_scene_name = self.rendering_scene.name

        #copy sequence to new scene and set up scene
        bpy.ops.sequencer.paste()
        temp_sequence = self.rendering_scene.sequence_editor.sequences[0]
        copy_curves(sequence, temp_sequence, self.original_scene, self.rendering_scene)
        self.rendering_scene.frame_start = temp_sequence.frame_final_start
        self.rendering_scene.frame_end = temp_sequence.frame_final_end - 1
        filename = sequence.name
        if self.original_scene.vseqf.batch_render_directory:
            path = self.original_scene.vseqf.batch_render_directory
        else:
            path = self.rendering_scene.render.filepath
        self.rendering_scene.render.filepath = os.path.join(path, filename)

        #render
        if sequence.type != 'SOUND':
            if sequence.blend_type in ['OVER_DROP', 'ALPHA_OVER']:
                transparent = True
                setting = self.original_scene.vseqf.transparent_settings_menu
            else:
                transparent = False
                setting = self.original_scene.vseqf.video_settings_menu
            self.set_render_settings(self.rendering_scene, setting, transparent)

            if not self.original_scene.vseqf.batch_effects:
                temp_sequence.modifiers.clear()
            self.file = self.rendering_scene.render.frame_path(frame=1)
            bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
            self.rendering_scene.vseqf.batch_rendering = True
            if 'batch_render_complete_handler' not in str(bpy.app.handlers.render_complete):
                bpy.app.handlers.render_complete.append(batch_render_complete_handler)
            if 'batch_render_cancel_handler' not in str(bpy.app.handlers.render_cancel):
                bpy.app.handlers.render_cancel.append(batch_render_cancel_handler)
            if self._timer:
                bpy.context.window_manager.event_timer_remove(self._timer)
            self._timer = bpy.context.window_manager.event_timer_add(1, bpy.context.window)
        else:
            audio_format = self.original_scene.vseqf.audio_settings_menu
            if audio_format == 'FLAC':
                extension = '.flac'
                container = 'FLAC'
                codec = 'FLAC'
            elif audio_format == 'MP3':
                extension = '.mp3'
                container = 'MP3'
                codec = 'MP3'
            elif audio_format == 'OGG':
                extension = '.ogg'
                container = 'OGG'
                codec = 'VORBIS'
            else:  #audio_format == 'WAV'
                extension = '.wav'
                container = 'WAV'
                codec = 'PCM'
            bpy.ops.sound.mixdown(filepath=self.rendering_scene.render.filepath+extension, format='S16', bitrate=192, container=container, codec=codec)
            self.file = self.rendering_scene.render.filepath+extension
            self.rendering_scene.vseqf.batch_rendering = False
            if self._timer:
                bpy.context.window_manager.event_timer_remove(self._timer)
            self._timer = bpy.context.window_manager.event_timer_add(1, bpy.context.window)

    def copy_settings(self, sequence, new_sequence):
        """Copies the needed settings from the original sequence to the newly imported sequence
        Arguments:
            sequence: VSE Sequence, the original
            new_sequence: VSE Sequence, the sequence to copy the settings to"""

        new_sequence.lock = sequence.lock
        new_sequence.parent = sequence.parent
        new_sequence.blend_alpha = sequence.blend_alpha
        new_sequence.blend_type = sequence.blend_type
        if new_sequence.type != 'SOUND':
            new_sequence.alpha_mode = sequence.alpha_mode

    def finish_render(self):
        """Finishes the process of rendering a sequence by replacing the original sequence, and deleting the temporary scene"""
        bpy.context.screen.scene = self.rendering_scene
        try:
            bpy.ops.render.view_cancel()
        except:
            pass
        if self.rendering_sequence.type != 'SOUND':
            file_format = self.rendering_scene.render.image_settings.file_format
            if file_format in ['AVI_JPEG', 'AVI_RAW', 'FRAMESERVER', 'H264', 'FFMPEG', 'THEORA', 'XVID']:
                #delete temporary scene
                bpy.ops.scene.delete()
                bpy.context.screen.scene = self.original_scene
                new_sequence = self.original_scene.sequence_editor.sequences.new_movie(name=self.rendering_sequence.name+' rendered', filepath=self.file, channel=self.rendering_sequence.channel, frame_start=self.rendering_sequence.frame_final_start)
            else:
                files = []
                for frame in range(2, self.rendering_scene.frame_end):
                    files.append(os.path.split(self.rendering_scene.render.frame_path(frame=frame))[1])
                #delete temporary scene
                bpy.ops.scene.delete()
                bpy.context.screen.scene = self.original_scene
                new_sequence = self.original_scene.sequence_editor.sequences.new_image(name=self.rendering_sequence.name+' rendered', filepath=self.file, channel=self.rendering_sequence.channel, frame_start=self.rendering_sequence.frame_final_start)
                for file in files:
                    new_sequence.elements.append(file)
        else:
            #delete temporary scene
            bpy.ops.scene.delete()
            bpy.context.screen.scene = self.original_scene

            new_sequence = self.original_scene.sequence_editor.sequences.new_sound(name=self.rendering_sequence.name+' rendered', filepath=self.file, channel=self.rendering_sequence.channel, frame_start=self.rendering_sequence.frame_final_start)
        #replace sequence
        bpy.ops.sequencer.select_all(action='DESELECT')
        self.copy_settings(self.rendering_sequence, new_sequence)
        self.rendering_sequence.select = True
        new_sequence.select = True
        self.original_scene.sequence_editor.active_strip = self.rendering_sequence

        for other_sequence in self.original_scene.sequence_editor.sequences_all:
            if hasattr(other_sequence, 'input_1'):
                if other_sequence.input_1 == self.rendering_sequence:
                    other_sequence.input_1 = new_sequence
            if hasattr(other_sequence, 'input_2'):
                if other_sequence.input_2 == self.rendering_sequence:
                    other_sequence.input_2 = new_sequence
        if not self.original_scene.vseqf.batch_effects:
            bpy.ops.sequencer.strip_modifier_copy(type='REPLACE')

        new_sequence.select = False
        bpy.ops.sequencer.delete()

    def next_render(self):
        """Starts rendering the next sequence in the list"""

        sequence = self.renders.pop(0)
        print('rendering '+sequence.name)
        self.render_sequence(sequence)

    def modal(self, context, event):
        """Main modal function, handles the render list"""

        if not self.rendering_scene:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            return {'CANCELLED'}
        if not bpy.data.scenes.get(self.rendering_scene_name, False):
            #the user deleted the rendering scene, uh-oh... blender will crash now.
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            return {'CANCELLED'}
        if event.type == 'TIMER':
            if not self.rendering_scene.vseqf.batch_rendering:
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
                    self._timer = None
                self.finish_render()
                if len(self.renders) > 0:
                    self.next_render()
                    self.report({'INFO'}, "Rendered "+str(self.total_renders - len(self.renders))+" out of "+str(self.total_renders)+" files.  "+str(self.total_frames)+" frames total.")
                else:
                    return {'FINISHED'}

            return {'PASS_THROUGH'}
        if self.rendering_scene.vseqf.batch_rendering_cancel:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            self.renders.clear()
            try:
                bpy.ops.render.view_cancel()
            except:
                pass
            try:
                self.rendering_scene.user_clear()
                bpy.data.scenes.remove(self.rendering_scene)
                context.screen.scene = self.original_scene
                context.screen.scene.update()
                context.window_manager.update_tag()
            except:
                pass
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        """Called when the batch render is initialized.  Sets up variables and begins the rendering process."""

        del event
        context.window_manager.modal_handler_add(self)
        self.rendering = False
        oldscene = context.scene
        vseqf = oldscene.vseqf
        name = oldscene.name + ' Batch Render'
        bpy.ops.scene.new(type='FULL_COPY')
        newscene = context.scene
        newscene.name = name

        if vseqf.batch_meta == 'SUBSTRIPS':
            old_sequences = newscene.sequence_editor.sequences_all
        else:
            old_sequences = newscene.sequence_editor.sequences

        #queue up renders
        self.total_frames = 0
        self.audio_frames = 0
        self.renders = []
        for sequence in old_sequences:
            if (vseqf.batch_selected and sequence.select) or not vseqf.batch_selected:
                if sequence.type == 'MOVIE' or sequence.type == 'IMAGE' or sequence.type == 'MOVIECLIP':
                    #standard video or image sequence
                    self.renders.append(sequence)
                    self.total_frames = self.total_frames + sequence.frame_final_duration
                elif sequence.type == 'SOUND':
                    #audio sequence
                    if vseqf.batch_audio:
                        self.renders.append(sequence)
                        self.audio_frames = self.audio_frames + sequence.frame_final_duration
                elif sequence.type == 'META':
                    #meta sequence
                    if vseqf.batch_meta == 'SINGLESTRIP':
                        self.renders.append(sequence)
                        self.total_frames = self.total_frames + sequence.frame_final_duration
                else:
                    #other sequence type, not handled
                    pass
        self.total_renders = len(self.renders)
        if self.total_renders > 0:
            self.next_render()
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}


#Functions and classes related to QuickTags
def populate_selected_tags():
    vseqf = bpy.context.scene.vseqf
    selected_sequences = current_selected(bpy.context)
    vseqf.selected_tags.clear()
    populate_tags(sequences=selected_sequences, tags=vseqf.selected_tags)


def populate_tags(sequences=False, tags=False):
    """Iterates through all sequences and stores all tags to the 'tags' property group
    If no sequences are given, default to all sequences in context.
    If no tags group is given, default to scene.vseqf.tags"""

    if sequences is False:
        sequences = current_sequences(bpy.context)
    if tags is False:
        tags = bpy.context.scene.vseqf.tags

    temp_tags = set()
    for sequence in sequences:
        for tag in sequence.tags:
            temp_tags.add(tag.text)
    tags.clear()
    add_tags = sorted(temp_tags)
    for tag in add_tags:
        new_tag = tags.add()
        new_tag.text = tag


class VSEQFQuickTagsMenu(bpy.types.Menu):
    bl_idname = 'vseqf.quicktags_menu'
    bl_label = "Tags"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for sequences
        if not context.sequences or not context.scene.sequence_editor:
            return False
        if len(context.sequences) > 0 and context.scene.sequence_editor.active_strip:
            return prefs.tags
        else:
            return False

    def draw(self, context):
        layout = self.layout
        active = current_active(context)
        if active:
            for tag in active.tags:
                layout.operator('vseqf.quicktags_select', text=tag.text).text = tag.text


class VSEQFQuickTagsPanel(bpy.types.Panel):
    """Panel for displaying, removing and adding tags"""

    bl_label = "Quick Tags"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for sequences
        if not context.sequences or not context.scene.sequence_editor:
            return False
        if len(context.sequences) > 0 and context.scene.sequence_editor.active_strip:
            return prefs.tags
        else:
            return False

    def draw(self, context):
        scene = context.scene
        vseqf = scene.vseqf
        sequence = current_active(context)
        layout = self.layout
        row = layout.row()
        row.label('All Tags:')
        row = layout.row()
        row.template_list("VSEQFQuickTagListAll", "", vseqf, 'tags', vseqf, 'marker_index')
        row = layout.row()
        split = row.split(percentage=.9, align=True)
        split.prop(vseqf, 'current_tag')
        split.operator('vseqf.quicktags_add', text="", icon="PLUS").text = vseqf.current_tag
        row = layout.row()
        split = row.split(percentage=.5)
        if vseqf.show_selected_tags:
            populate_selected_tags()
            split.label('Selected Tags:')
            split.prop(vseqf, 'show_selected_tags', text='Show All Selected', toggle=True)
            row = layout.row()
            row.template_list("VSEQFQuickTagList", "", vseqf, 'selected_tags', vseqf, 'marker_index', rows=2)
        else:
            split.label('Active Tags:')
            split.prop(vseqf, 'show_selected_tags', text='Show All Selected', toggle=True)
            row = layout.row()
            row.template_list("VSEQFQuickTagList", "", sequence, 'tags', vseqf, 'marker_index', rows=2)
        row = layout.row()
        row.operator('vseqf.quicktags_clear', text='Clear Selected Tags')


class VSEQFQuickTagListAll(bpy.types.UIList):
    """Draws a list of tags"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(percentage=.9, align=True)
        split.operator('vseqf.quicktags_select', text=item.text).text = item.text
        split.operator('vseqf.quicktags_add', text='', icon="PLUS").text = item.text

    def draw_filter(self, context, layout):
        pass


class VSEQFQuickTagList(bpy.types.UIList):
    """Draws an editable list of tags"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(percentage=.9, align=True)
        split.operator('vseqf.quicktags_select', text=item.text).text = item.text
        split.operator('vseqf.quicktags_remove', text='', icon='X').text = item.text

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, property):
        del context
        tags = getattr(data, property)
        helper = bpy.types.UI_UL_list
        flt_neworder = helper.sort_items_by_name(tags, 'text')
        return [], flt_neworder


class VSEQFQuickTagsClear(bpy.types.Operator):
    """Clears all tags on the selected and active sequences"""

    bl_idname = 'vseqf.quicktags_clear'
    bl_label = 'VSEQF Quick Tags Clear'
    bl_description = 'Clear all tags on all selected sequences'

    def execute(self, context):
        sequences = current_selected(context)
        if not sequences:
            return {'FINISHED'}
        bpy.ops.ed.undo_push()
        for sequence in sequences:
            sequence.tags.clear()
        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsSelect(bpy.types.Operator):
    """Selects sequences with the given tag name
    Argument:
        text: String, the name of the tag to find sequences with"""

    bl_idname = 'vseqf.quicktags_select'
    bl_label = 'VSEQF Quick Tags Select'
    bl_description = 'Select all sequences with this tag'

    text = bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        new_active = None
        sequences = current_sequences(context)
        for sequence in sequences:
            sequence.select = False
            for tag in sequence.tags:
                if tag.text == self.text:
                    sequence.select = True
                    new_active = sequence
                    break
        active = current_active(context)
        if not active and not active.select and new_active:
            context.scene.sequence_editor.active_strip = new_active
        context.scene.vseqf.current_tag = self.text
        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsRemoveFrom(bpy.types.Operator):
    """Removes a tag from a specified sequence
    Argument:
        tag: String, a tag and sequence name separated by a next line"""
    bl_idname = 'vseqf.quicktags_remove_from'
    bl_label = 'VSEQF Quick Tags Remove From'
    bl_description = 'Remove this tag from this sequence'

    tag = bpy.props.StringProperty()

    def execute(self, context):
        if '\n' in self.tag:
            text, sequence_name = self.tag.split('\n')
            if text and sequence_name:
                bpy.ops.ed.undo_push()
                sequences = current_sequences(context)
                for sequence in sequences:
                    if sequence.name == sequence_name:
                        for index, tag in reversed(list(enumerate(sequence.tags))):
                            if tag.text == text:
                                sequence.tags.remove(index)

        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsRemove(bpy.types.Operator):
    """Remove tags with a specific name from all selected sequences
    Argument:
        text: String, tag text to remove"""
    bl_idname = 'vseqf.quicktags_remove'
    bl_label = 'VSEQF Quick Tags Remove'
    bl_description = 'Remove this tag from all selected sequences'

    text = bpy.props.StringProperty()

    def execute(self, context):
        sequences = current_selected(context)
        active = current_active(context)
        if active:
            sequences.append(active)
        bpy.ops.ed.undo_push()
        for sequence in sequences:
            for index, tag in reversed(list(enumerate(sequence.tags))):
                if tag.text == self.text:
                    sequence.tags.remove(index)

        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsAdd(bpy.types.Operator):
    """Adds a tag with the given text to the selected and active sequences
    Argument:
        text: String, tag to add"""
    bl_idname = 'vseqf.quicktags_add'
    bl_label = 'VSEQF Quick Tags Add'
    bl_description = 'Add this tag to all selected sequences'

    text = bpy.props.StringProperty()

    def execute(self, context):
        text = self.text.replace("\n", '')
        if text:
            bpy.ops.ed.undo_push()
            sequences = current_selected(context)
            for sequence in sequences:
                tag_found = False
                for tag in sequence.tags:
                    if tag.text == text:
                        tag_found = True
                if not tag_found:
                    tag = sequence.tags.add()
                    tag.text = text

            populate_tags()
        return{'FINISHED'}


#Functions and Classes related to QuickCuts
def vseqf_cut(sequence, frame=0, cut_type="SOFT"):
    bpy.ops.sequencer.select_all(action='DESELECT')
    left_sequence = False
    right_sequence = False
    if frame > sequence.frame_final_start and frame < sequence.frame_final_end:
        sequence.select = True
        bpy.ops.sequencer.cut(frame=frame, type=cut_type, side="BOTH")
        sequences = current_selected(bpy.context)
        for seq in sequences:
            seq.select = False
            if seq.frame_final_start < frame:
                left_sequence = seq
            else:
                right_sequence = seq
    else:
        if sequence.frame_final_end <= frame:
            left_sequence = sequence
        else:
            right_sequence = sequence
    return left_sequence, right_sequence


class VSEQFCut(bpy.types.Operator):
    """Advanced cut operator with many extra operations.
    Operator variables:
        frame: The frame to perform the cut operation at
        side: determines which side of the frame some cut functions select or work on.  If this operator is invoked, this will be determined automatically based on mouse position relative to the frame.  Defaults to BOTH.
        type: tells the operator what cut operation to perform, options are:
            SOFT: standard cut (like pressing 'k')
            HARD: hard cut (like pressing 'shift-k')
            INSERT: will perform a standard cut, then ripple insert empty frames.
            INSERT_ONLY: will ripple insert empty frames without performing a cut
            TRIM: will cut off one side of the strip and delete it.  This mode will not run if side==BOTH.
            TRIM_LEFT: trim to the left
            TRIM_RIGHT: trim to the right
            SLIDE: will cut off one side of the strip, and slide the remaining strip up to fill the space.  This mode will not run if side==BOTH.
            SLIDE_LEFT: slide to the left
            SLIDE_RIGHT: slide to the right
            RIPPLE: will cut off one side of the strip, and slide it and/or all following strips back to fill the empty space.  This mode will not run if side==BOTH.
            RIPPLE_LEFT: ripple to the left
            RIPPLE_RIGHT: ripple to the right
            UNCUT: if the strip to the left or right is the same source and in the same position, the strip will be merged into the current one.  This mode will not run if side==BOTH.
            UNCUT_LEFT: Uncut, to the left
            UNCUT_RIGHT: Uncut, to the right"""

    bl_idname = "vseqf.cut"
    bl_label = "Wrapper for the built in sequence cut operator that maintains parenting relationships and provides extra cut operations."

    frame = bpy.props.IntProperty()
    use_frame = bpy.props.BoolProperty(default=False)
    type = bpy.props.EnumProperty(name='Type', items=[("SOFT", "Soft", "", 1), ("HARD", "Hard", "", 2), ("INSERT", "Insert Cut", "", 3), ("INSERT_ONLY", "Insert Only", "", 4), ("TRIM", "Trim", "", 5), ("TRIM_LEFT", "Trim Left", "", 6), ("TRIM_RIGHT", "Trim Right", "", 7), ("SLIDE", "Slide", "", 8), ("SLIDE_LEFT", "Slide Left", "", 9), ("SLIDE_RIGHT", "Slide Right", "", 10), ("RIPPLE", "Ripple", "", 11), ("RIPPLE_LEFT", "Ripple Left", "", 12), ("RIPPLE_RIGHT", "Ripple Right", "", 13), ("UNCUT", "UnCut", "", 14), ("UNCUT_LEFT", "UnCut Left", "", 15), ("UNCUT_RIGHT", "UnCut Right", "", 16)], default='SOFT')
    side = bpy.props.EnumProperty(name='Side', items=[("BOTH", "Both", "", 1), ("RIGHT", "Right", "", 2), ("LEFT", "Left", "", 3)], default='BOTH')
    all = bpy.props.BoolProperty(name='Cut All', default=False)
    use_all = bpy.props.BoolProperty(default=False)
    insert = bpy.props.IntProperty(0)
    use_insert = bpy.props.BoolProperty(default=False)

    def __init__(self):
        if not self.use_frame:
            self.frame = bpy.context.scene.frame_current

    def reset(self):
        #resets the variables after a cut is performed
        self.frame = 0
        self.type = 'SOFT'
        self.side = 'BOTH'
        self.all = False
        self.use_all = False
        self.insert = 0
        self.use_insert = False
        self.use_frame = False

    def delete_sequence(self, sequence):
        """Deletes a sequence while maintaining previous selected and active sequences
        Argument:
            sequence: VSE Sequence object to delete"""

        active = current_active(bpy.context)
        selected = []
        for seq in bpy.context.scene.sequence_editor.sequences:
            if seq.select:
                selected.append(seq)
                seq.select = False
        sequence.select = True
        bpy.ops.sequencer.delete()
        for seq in selected:
            seq.select = True
        if active:
            bpy.context.scene.sequence_editor.active_strip = active

    def check_source(self, sequence, next_sequence):
        """Used by UnCut, checks the source and position of two sequences to see if they can be merged

        Arguments:
            sequence: VSE Sequence object to be compared
            next_sequence: VSE Sequence object to be compared

        Returns: Boolean"""

        if sequence.type == next_sequence.type:
            if sequence.type == 'IMAGE':
                if sequence.directory == next_sequence.directory and sequence.elements[0].filename == next_sequence.elements[0].filename:
                    if len(sequence.elements) == 1 and len(next_sequence.elements) == 1:
                        return True
                    elif sequence.frame_start == next_sequence.frame_start:
                        return True
            elif sequence.frame_start == next_sequence.frame_start:
                if sequence.type == 'SOUND':
                    if sequence.sound.filepath == next_sequence.sound.filepath:
                        return True
                if sequence.type == 'MOVIE':
                    if sequence.filepath == next_sequence.filepath:
                        return True
                if sequence.type == 'SCENE':
                    if sequence.scene == next_sequence.scene:
                        return True
                if sequence.type == 'MOVIECLIP':

                    #no way of checking source file :\
                    pass
        return False

    def execute(self, context):
        self.cut(context)
        return{'FINISHED'}

    def invoke(self, context, event):
        mouse_x = event.mouse_region_x
        cut_frame = self.frame
        region = context.region
        view = region.view2d
        cursor, bottom = view.view_to_region(cut_frame, 0, clip=False)
        if mouse_x < cursor:
            side = 'LEFT'
        else:
            side = 'RIGHT'
        self.cut(context, side)
        return{'FINISHED'}

    def cut(self, context, side="BOTH"):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            self.reset()
            return
        bpy.ops.ed.undo_push()
        if not self.use_all:
            self.all = context.scene.vseqf.quickcuts_all
        if self.type == 'UNCUT_LEFT':
            self.type = 'UNCUT'
            side = 'LEFT'
        if self.type == 'UNCUT_RIGHT':
            self.type = 'UNCUT'
            side = 'RIGHT'
        if self.type == 'TRIM_LEFT':
            self.type = 'TRIM'
            side = 'LEFT'
        if self.type == 'TRIM_RIGHT':
            self.type = 'TRIM'
            side = 'RIGHT'
        if self.type == 'SLIDE_LEFT':
            self.type = 'SLIDE'
            side = 'LEFT'
        if self.type == 'SLIDE_RIGHT':
            self.type = 'SLIDE'
            side = 'RIGHT'
        if self.type == 'RIPPLE_LEFT':
            self.type = 'RIPPLE'
            side = 'LEFT'
        if self.type == 'RIPPLE_RIGHT':
            self.type = 'RIPPLE'
            side = 'RIGHT'
        sequences = current_sequences(context)
        active = current_active(context)
        to_cut = []
        to_select = []
        to_active = None
        to_change = []
        cut_pairs = []

        #determine all sequences available to cut
        to_cut_temp = []
        for sequence in sequences:
            if not sequence.lock and (under_cursor(sequence, self.frame) or self.type == 'UNCUT') and (not hasattr(sequence, 'input_1')):
                if self.all:
                    to_cut_temp.append(sequence)
                elif sequence.select:
                    to_cut_temp.append(sequence)
                    if vseqf_parenting():
                        children = get_recursive(sequence, [])
                        for child in children:
                            if not child.lock and (not hasattr(child, 'input_1')) and child not in to_cut_temp:
                                to_cut_temp.append(child)

        #find the ripple amount
        ripple_amount = 0
        for sequence in to_cut_temp:
            if side == 'LEFT':
                cut_amount = self.frame - sequence.frame_final_start
            else:
                cut_amount = sequence.frame_final_end - self.frame
            to_cut.append(sequence)
            if cut_amount > ripple_amount:
                ripple_amount = cut_amount

        bpy.ops.sequencer.select_all(action='DESELECT')
        for sequence in to_cut:
            left = False
            right = False
            if self.type == 'UNCUT':
                to_select.append(sequence)
                if side != 'BOTH':
                    if side == 'LEFT':
                        direction = 'previous'
                    else:
                        direction = 'next'
                    merge_to = find_close_sequence(sequences, sequence, direction=direction, mode='channel', sounds=True)
                    if merge_to:
                        if not merge_to.lock:
                            source_matches = self.check_source(sequence, merge_to)
                            if source_matches:
                                merge_to_children = find_children(merge_to)
                                add_children(sequence, merge_to_children)
                                clear_children(merge_to)
                                if direction == 'next':
                                    newend = merge_to.frame_final_end
                                    self.delete_sequence(merge_to)
                                    sequence.frame_final_end = newend
                                else:
                                    newstart = merge_to.frame_final_start
                                    self.delete_sequence(merge_to)
                                    sequence.frame_final_start = newstart
            if self.type in ['TRIM', 'SLIDE', 'RIPPLE']:
                if side != 'BOTH':
                    if side == 'LEFT':
                        sequence.frame_final_start = self.frame
                        to_select.append(sequence)
                        if self.type == 'SLIDE':
                            sequence.frame_start = sequence.frame_start - ripple_amount
                    else:
                        sequence.frame_final_end = self.frame
                        to_select.append(sequence)
                        if self.type == 'SLIDE':
                            sequence.frame_start = sequence.frame_start + ripple_amount
                else:
                    ripple_amount = 0

            if self.type in ['SOFT', 'HARD', 'INSERT']:
                if self.type == 'INSERT':
                    cut_type = 'SOFT'
                else:
                    cut_type = self.type
                left, right = vseqf_cut(sequence=sequence, frame=self.frame, cut_type=cut_type)
                cut_pairs.append([left, right])
                if right and self.type == 'INSERT':
                    to_change.append([right, right.channel, right.frame_start + context.scene.vseqf.quickcuts_insert, True])
            else:
                to_select.append(sequence)
            if (side == 'LEFT' or side == 'BOTH') and left:
                to_select.append(left)
                if active and left == active:
                    to_active = left
            if (side == 'RIGHT' or side == 'BOTH') and right:
                to_select.append(right)
                if active and left == active and side != 'BOTH':
                    to_active = right
        fix_effects(cut_pairs, sequences)

        #fix parenting of cut sequences
        for cut_pair in cut_pairs:
            left, right = cut_pair
            if right:
                parent_pair = self.find_parent(right.parent, cut_pairs)
                if parent_pair:
                    if parent_pair[1]:
                        right.parent = parent_pair[1].name

        if self.type == 'INSERT' or self.type == 'RIPPLE' or self.type == 'INSERT_ONLY':
            if self.type == 'RIPPLE':
                insert = 0 - ripple_amount
            else:
                if self.use_insert:
                    insert = self.insert
                else:
                    insert = context.scene.vseqf.quickcuts_insert
            if not (self.type == 'INSERT' and not self.all):
                to_change = []
                sequences = current_sequences(context)
                for sequence in sequences:
                    if sequence.frame_final_start >= self.frame:
                        #children = find_children(sequence)
                        #for child in children:
                        #    if child.frame_final_start < self.frame:
                        #        child.frame_start = child.frame_start + insert
                        to_change.append([sequence, sequence.channel, sequence.frame_start + insert, True])
        else:
            for sequence in to_select:
                if sequence:
                    sequence.select = True
        for seq in to_change:
            sequence = seq[0]
            sequence.channel = seq[1]
            if not hasattr(sequence, 'input_1'):
                sequence.frame_start = seq[2]
            sequence.select = True
            if (sequence.frame_start != seq[2] or sequence.channel != seq[1]) and seq[3]:
                seq[3] = False
                to_change.append(seq)
        if to_active:
            context.scene.sequence_editor.active_strip = to_active
        if side == 'LEFT':
            if self.type in ['RIPPLE', 'SLIDE']:
                context.scene.frame_current = context.scene.frame_current - ripple_amount
        else:
            if self.type in ['SLIDE']:
                context.scene.frame_current = context.scene.frame_current + ripple_amount
        self.reset()

    def find_parent(self, parent_name, cut_pairs):
        for pair in cut_pairs:
            if pair[0] and pair[0].name == parent_name:
                return pair
        return None


class VSEQFQuickTimelineMenu(bpy.types.Menu):
    bl_idname = "vsqf.quicktimeline_menu"
    bl_label = "Timeline"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator('vseqf.quicktimeline', text='Timeline To All').operation = 'sequences'
        layout.operator('vseqf.quicktimeline', text='Timeline To Selected').operation = 'selected'
        layout.separator()
        layout.operator('vseqf.quicktimeline', text='Timeline Start To All').operation = 'sequences_start'
        layout.operator('vseqf.quicktimeline', text='Timeline End To All').operation = 'sequences_end'
        layout.operator('vseqf.quicktimeline', text='Timeline Start To Selected').operation = 'selected_start'
        layout.operator('vseqf.quicktimeline', text='Timeline End To Selected').operation = 'selected_end'
        row = layout.row()
        row.operator('vseqf.quicktimeline', text='Full Timeline Setup').operation = 'full_auto'
        row.enabled = not inside_meta_strip()


class VSEQFQuickCutsMenu(bpy.types.Menu):
    """Popup Menu for QuickCuts operators and properties"""

    bl_idname = "vseqf.quickcuts_menu"
    bl_label = "Quick Cuts"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for sequences
        if not context.sequences or not context.scene.sequence_editor:
            return False
        if len(context.sequences) > 0:
            return prefs.cuts
        else:
            return False

    def draw(self, context):
        layout = self.layout
        layout.operator('vseqf.cut', text='Cut').type = 'SOFT'
        layout.operator('vseqf.cut', text='Cut Insert').type = 'INSERT'
        layout.operator('vseqf.cut', text='UnCut Left', icon='BACK').type = 'UNCUT_LEFT'
        layout.operator('vseqf.cut', text='UnCut Right', icon='FORWARD').type = 'UNCUT_RIGHT'
        layout.operator('vseqf.delete', text='Delete', icon='X')
        layout.operator('vseqf.delete', text='Ripple Delete', icon='X').ripple = True
        layout.separator()
        layout.operator('vseqf.cut', text='Trim Left', icon='BACK').type = 'TRIM_LEFT'
        layout.operator('vseqf.cut', text='Trim Right', icon='FORWARD').type = 'TRIM_RIGHT'
        layout.operator('vseqf.cut', text='Slide Trim Left', icon='BACK').type = 'SLIDE_LEFT'
        layout.operator('vseqf.cut', text='Slide Trim Right', icon='FORWARD').type = 'SLIDE_RIGHT'
        layout.operator('vseqf.cut', text='Ripple Trim Left', icon='BACK').type = 'RIPPLE_LEFT'
        layout.operator('vseqf.cut', text='Ripple Trim Right', icon='FORWARD').type = 'RIPPLE_RIGHT'
        layout.separator()
        layout.prop(context.scene.vseqf, 'quickcuts_all', toggle=True)
        layout.prop(context.scene.vseqf, 'quickcuts_insert')
        layout.menu(VSEQFQuickTimelineMenu.bl_idname)


class VSEQFQuickCutsPanel(bpy.types.Panel):
    """Panel for QuickCuts operators and properties"""

    bl_label = "Quick Cuts"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        #Check if panel is disabled
        if __name__ in context.user_preferences.addons:
            prefs = context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        #Check for sequences
        if not context.sequences or not context.scene.sequence_editor:
            return False
        if len(context.sequences) > 0:
            return prefs.cuts
        else:
            return False

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(context.scene.vseqf, 'quickcuts_all', toggle=True)
        row.prop(context.scene.vseqf, 'quickcuts_insert')
        box = layout.box()
        row = box.row()
        row.operator('vseqf.cut', text='Cut').type = 'SOFT'
        row.operator('vseqf.cut', text='Cut Insert').type = 'INSERT'
        row = box.row(align=True)
        row.operator('vseqf.cut', text='UnCut Left', icon='BACK').type = 'UNCUT_LEFT'
        row.operator('vseqf.cut', text='UnCut Right', icon='FORWARD').type = 'UNCUT_RIGHT'
        row = box.row()
        row.operator('vseqf.delete', text='Delete', icon='X')
        row.operator('vseqf.delete', text='Ripple Delete', icon='X').ripple = True

        box = layout.box()
        row = box.row()
        split = row.split(percentage=.5, align=True)
        column = split.column(align=True)
        column.operator('vseqf.cut', text='Trim Left', icon='BACK').type = 'TRIM_LEFT'
        column.operator('vseqf.cut', text='Slide Trim Left', icon='BACK').type = 'SLIDE_LEFT'
        column.operator('vseqf.cut', text='Ripple Trim Left', icon='BACK').type = 'RIPPLE_LEFT'

        column = split.column(align=True)
        column.operator('vseqf.cut', text='Trim Right', icon='FORWARD').type = 'TRIM_RIGHT'
        column.operator('vseqf.cut', text='Slide Trim Right', icon='FORWARD').type = 'SLIDE_RIGHT'
        column.operator('vseqf.cut', text='Ripple Trim Right', icon='FORWARD').type = 'RIPPLE_RIGHT'

        box = layout.box()
        row = box.row()
        split = row.split(percentage=.5, align=True)
        column = split.column(align=True)
        column.operator('vseqf.quicktimeline', text='Timeline To All').operation = 'sequences'
        column.operator('vseqf.quicktimeline', text='Start To All').operation = 'sequences_start'
        column.operator('vseqf.quicktimeline', text='Start To Selected').operation = 'selected_start'

        column = split.column(align=True)
        column.operator('vseqf.quicktimeline', text='Timeline To Selected').operation = 'selected'
        column.operator('vseqf.quicktimeline', text='End To All').operation = 'sequences_end'
        column.operator('vseqf.quicktimeline', text='End To Selected').operation = 'selected_end'
        row = box.row()
        row.operator('vseqf.quicktimeline', text='Full Timeline Setup').operation = 'full_auto'
        row.enabled = not inside_meta_strip()


class VSEQFDelete(bpy.types.Operator):
    """Operator to perform sequencer delete operations, while handling parents and rippling."""

    bl_idname = 'vseqf.delete'
    bl_label = 'VSEQF Delete'

    ripple = bpy.props.BoolProperty(default=False)

    def reset(self):
        self.ripple = False

    def execute(self, context):
        bpy.ops.ed.undo_push()
        sequences = current_selected(context)
        if not sequences:
            return {'CANCELLED'}
        first_start = sequences[0].frame_final_start
        for sequence in sequences:
            if sequence.frame_final_start < first_start:
                first_start = sequence.frame_final_start
            offset = sequence.frame_final_duration
            end_frame = sequence.frame_final_end
            to_delete = [sequence]
            if vseqf_parenting() and context.scene.vseqf.delete_children:
                children = find_children(sequence)
                for child in children:
                    if child not in sequences:
                        to_delete.append(child)
            bpy.ops.sequencer.select_all(action='DESELECT')
            for delete in to_delete:
                delete.select = True
            bpy.ops.sequencer.delete()
            if self.ripple:
                all_sequences = current_sequences(context)

                #cache channels
                update_sequences_data = []
                for seq in all_sequences:
                    update_sequences_data.append([seq, seq.channel])
                for seq_data in update_sequences_data:
                    seq, last_channel = seq_data
                    #move sequences
                    if seq.frame_final_start >= end_frame:
                        seq.frame_start = seq.frame_start - offset
                for seq_data in update_sequences_data:
                    seq, last_channel = seq_data
                    seq.channel = last_channel
        if self.ripple:
            context.scene.frame_current = first_start
        self.reset()
        return {'FINISHED'}


class VSEQFQuickTimeline(bpy.types.Operator):
    """Operator to adjust the VSE timeline in various ways

    Argument:
        operation: String, the operation to be performed.
            'sequences': Trims the timeline to all sequences in the VSE.  If no sequences are loaded, timeline is not changed.
            'selected': Trims the timeline to the selected sequence(s) in the VSE.  If no sequences are selected, timeline is not changed.
            'sequences_start': Like 'sequences', but only trims the start frame.
            'sequences_end': Like 'sequences, but only trims the end frame.
            'selected_start': Like 'selected', but only trims the start frame.
            'selected_end': Like 'selected', but only trims the end frame.
            'full_auto': moves sequences back or up to match with frame 1, then sets start and end to encompass all sequences."""

    bl_idname = 'vseqf.quicktimeline'
    bl_label = 'VSEQF Quick Timeline'

    operation = bpy.props.StringProperty()

    def execute(self, context):
        operation = self.operation
        if 'selected' in operation:
            sequences = current_selected(context)
        else:
            sequences = current_sequences(context)
        if sequences:
            bpy.ops.ed.undo_push()
            if operation == 'full_auto':
                start_frame = find_sequences_start(sequences)
                end_frame = find_sequences_end(sequences)
                if start_frame != 1:
                    #move all sequences forward then back
                    offset_1 = end_frame - start_frame + 1
                    offset_2 = -offset_1 - start_frame + 1

                    for sequence in sequences:
                        if not hasattr(sequence, 'input_1'):
                            sequence.frame_start = sequence.frame_start + offset_1
                    for sequence in sequences:
                        if not hasattr(sequence, 'input_1'):
                            sequence.frame_start = sequence.frame_start + offset_2
                    sequences = current_sequences(context)
            starts = []
            ends = []
            for sequence in sequences:
                starts.append(sequence.frame_final_start)
                ends.append(sequence.frame_final_end)
            starts.sort()
            ends.sort()
            newstart = starts[0]
            newend = ends[-1] - 1
            scene = context.scene
            if ('start' in operation) and not ('end' in operation):
                #only set start point
                if scene.frame_end <= newstart:
                    scene.frame_end = newstart
                scene.frame_start = newstart
            elif ('end'in operation) and not ('start' in operation):
                #only set end point
                if scene.frame_start >= newend:
                    scene.frame_start = newend
                scene.frame_end = newend
            else:
                #set start and end
                scene.frame_start = newstart
                scene.frame_end = newend

        return{'FINISHED'}


#Classes for settings and variables
class VSEQFTags(bpy.types.PropertyGroup):
    """QuickTags property that stores tag information"""
    text = bpy.props.StringProperty(
        name="Tag Text",
        default="")


class VSEQFMarkerPreset(bpy.types.PropertyGroup):
    """Property for marker presets"""
    text = bpy.props.StringProperty(name="Text", default="")


class VSEQFSettingsMenu(bpy.types.Menu):
    """Pop-up menu for settings related to QuickContinuous"""
    bl_idname = "vseqf.settings_menu"
    bl_label = "Quick Settings"

    def draw(self, context):
        if __name__ in bpy.context.user_preferences.addons:
            prefs = bpy.context.user_preferences.addons[__name__].preferences
        else:
            prefs = VSEQFTempSettings()

        layout = self.layout
        scene = context.scene
        layout.prop(scene.vseqf, 'simplify_menus')
        layout.prop(scene.vseqf, 'grab_multiselect')
        layout.prop(scene.vseqf, 'snap_cursor_to_edge')
        layout.prop(scene.vseqf, 'snap_new_end')
        layout.prop(scene.vseqf, 'context')
        if prefs.parenting:
            layout.separator()
            layout.label('QuickParenting Settings')
            layout.separator()
            layout.prop(scene.vseqf, 'children')
            layout.prop(scene.vseqf, 'delete_children')
            layout.prop(scene.vseqf, 'autoparent')
            layout.prop(scene.vseqf, 'select_children')
        if prefs.proxy:
            layout.separator()
            layout.label('QuickProxy Settings')
            layout.separator()
            layout.prop(scene.vseqf, 'enable_proxy')
            layout.prop(scene.vseqf, 'build_proxy')
            layout.prop(scene.vseqf, "proxy_quality", text='Proxy Quality')
            layout.prop(scene.vseqf, "proxy_25", text='Generate 25% Proxy')
            layout.prop(scene.vseqf, "proxy_50", text='Generate 50% Proxy')
            layout.prop(scene.vseqf, "proxy_75", text='Generate 75% Proxy')
            layout.prop(scene.vseqf, "proxy_100", text='Generate 100% Proxy')


class VSEQFZoomPreset(bpy.types.PropertyGroup):
    """Property group to store a sequencer view position"""
    name = bpy.props.StringProperty(name="Preset Name", default="")
    left = bpy.props.FloatProperty(name="Leftmost Visible Frame", default=0.0)
    right = bpy.props.FloatProperty(name="Rightmost Visible Frame", default=300.0)
    bottom = bpy.props.FloatProperty(name="Bottom Visible Channel", default=0.0)
    top = bpy.props.FloatProperty(name="Top Visible Channel", default=5.0)


class VSEQFQuick3PointValues(bpy.types.PropertyGroup):
    import_frame_in = bpy.props.IntProperty(
        default=-1,
        min=-1)
    import_frame_length = bpy.props.IntProperty(
        default=-1,
        min=-1)
    import_minutes_in = bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_clip_import)
    import_seconds_in = bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_clip_import)
    import_frames_in = bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_clip_import)
    import_minutes_length = bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_clip_import)
    import_seconds_length = bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_clip_import)
    import_frames_length = bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_clip_import)


class VSEQFSetting(bpy.types.PropertyGroup):
    """Property group to store most VSEQF settings.  This will be assigned to scene.vseqf"""
    context = bpy.props.BoolProperty(
        name="Enable Context Menu",
        default=True)
    zoom_presets = bpy.props.CollectionProperty(type=VSEQFZoomPreset)
    last_frame = bpy.props.IntProperty(
        name="Last Scene Frame",
        default=1)
    video_settings_menu = bpy.props.EnumProperty(
        name="Video Render Setting",
        default='DEFAULT',
        items=[('DEFAULT', 'Scene Settings', '', 1), ('AVIJPEG', 'AVI JPEG', '', 2), ('H264', 'H264 Video', '', 3), ('JPEG', 'JPEG Sequence', '', 4), ('PNG', 'PNG Sequence', '', 5), ('TIFF', 'TIFF Sequence', '', 6), ('EXR', 'Open EXR Sequence', '', 7)])
    transparent_settings_menu = bpy.props.EnumProperty(
        name="Transparent Video Render Setting",
        default='DEFAULT',
        items=[('DEFAULT', 'Scene Settings', '', 1), ('AVIJPEG', 'AVI JPEG (No Transparency)', '', 2), ('H264', 'H264 Video (No Transparency)', '', 3), ('JPEG', 'JPEG Sequence (No Transparency)', '', 4), ('PNG', 'PNG Sequence', '', 5), ('TIFF', 'TIFF Sequence', '', 6), ('EXR', 'Open EXR Sequence', '', 7)])
    audio_settings_menu = bpy.props.EnumProperty(
        name="Audio Render Setting",
        default='FLAC',
        #mp3 export seems to be broken currently, (exports as extremely loud distorted garbage) so "('MP3', 'MP3 File', '', 4), " is removed for now
        items=[('FLAC', 'FLAC Audio', '', 1), ('WAV', 'WAV File', '', 2), ('OGG', 'OGG File', '', 3)])

    simplify_menus = bpy.props.BoolProperty(
        name="Simplify Sequencer Menus",
        default=True,
        description="Remove some items from the sequencer menus that require mouse input or are less useful.")

    batch_render_directory = bpy.props.StringProperty(
        name="Render Directory",
        default='./',
        description="Folder to batch render strips to.",
        subtype='DIR_PATH')
    batch_selected = bpy.props.BoolProperty(
        name="Render Only Selected",
        default=False)
    batch_effects = bpy.props.BoolProperty(
        name="Render Modifiers",
        default=True,
        description="If active, this will render modifiers to the export, if deactivated, modifiers will be copied.")
    batch_audio = bpy.props.BoolProperty(
        name="Render Audio",
        default=True,
        description="If active, this will render audio strips to a new file, if deactivated, audio strips will be copied over.")
    batch_meta = bpy.props.EnumProperty(
        name="Render Meta Strips",
        default='SINGLESTRIP',
        items=[('SINGLESTRIP', 'Single Strip', '', 1), ('SUBSTRIPS', 'Individual Substrips', '', 2), ('IGNORE', 'Ignore', '', 3)])
    batch_rendering = bpy.props.BoolProperty(
        name="Currently Rendering File",
        default=False)
    batch_rendering_cancel = bpy.props.BoolProperty(
        name="Canceled A Render",
        default=False)

    follow = bpy.props.BoolProperty(
        name="Cursor Following",
        default=False,
        update=start_follow)
    grab_multiselect = bpy.props.BoolProperty(
        name="Grab Multiple With Right-Click",
        default=False,
        description="Allows the right-click drag grab to work with multiple strips.")

    children = bpy.props.BoolProperty(
        name="Cut/Move Children",
        default=True,
        description="Automatically cut and move child strips along with a parent.")
    autoparent = bpy.props.BoolProperty(
        name="Auto-Parent New Audio To Video",
        default=True,
        description="Automatically parent audio strips to video when importing a movie with both types of strips.")
    select_children = bpy.props.BoolProperty(
        name="Auto-Select Children",
        default=False,
        description="Automatically select child strips when a parent is selected.")
    expanded_children = bpy.props.BoolProperty(default=True)
    delete_children = bpy.props.BoolProperty(
        name="Auto-Delete Children",
        default=False,
        description="Automatically delete child strips when a parent is deleted.")

    transition = bpy.props.EnumProperty(
        name="Transition Type",
        default="CROSS",
        items=[("CROSS", "Crossfade", "", 1), ("WIPE", "Wipe", "", 2), ("GAMMA_CROSS", "Gamma Cross", "", 3)])
    fade = bpy.props.IntProperty(
        name="Fade Length",
        default=0,
        min=0,
        description="Default Fade Length In Frames")
    fadein = bpy.props.IntProperty(
        name="Fade In Length",
        default=0,
        min=0,
        description="Current Fade In Length In Frames")
    fadeout = bpy.props.IntProperty(
        name="Fade Out Length",
        default=0,
        min=0,
        description="Current Fade Out Length In Frames")

    quicklist_parenting = bpy.props.BoolProperty(
        name="Parenting",
        default=True,
        description='Display parenting information')
    quicklist_tags = bpy.props.BoolProperty(
        name="Tags",
        default=True,
        description='Display tags')
    quicklist_editing = bpy.props.BoolProperty(
        name="Settings",
        default=False,
        description='Display position, length and proxy settings')
    quicklist_sort_reverse = bpy.props.BoolProperty(
        name='Reverse Sort',
        default=False,
        description='Reverse sort')
    quicklist_sort = bpy.props.EnumProperty(
        name="Sort Method",
        default='POSITION',
        items=[('POSITION', 'Position', '', 1), ('TITLE', 'Title', '', 2), ('LENGTH', 'Length', '', 3)])

    enable_proxy = bpy.props.BoolProperty(
        name="Enable Proxy On Import",
        default=False)
    build_proxy = bpy.props.BoolProperty(
        name="Auto-Build Proxy On Import",
        default=False)
    proxy_25 = bpy.props.BoolProperty(
        name="25%",
        default=True)
    proxy_50 = bpy.props.BoolProperty(
        name="50%",
        default=False)
    proxy_75 = bpy.props.BoolProperty(
        name="75%",
        default=False)
    proxy_100 = bpy.props.BoolProperty(
        name="100%",
        default=False)
    proxy_quality = bpy.props.IntProperty(
        name="Quality",
        default=90,
        min=1,
        max=100)

    current_marker_frame = bpy.props.IntProperty(
        default=0)
    marker_index = bpy.props.IntProperty(
        name="Marker Display Index",
        default=0)
    marker_presets = bpy.props.CollectionProperty(
        type=VSEQFMarkerPreset)
    expanded_markers = bpy.props.BoolProperty(default=True)
    current_marker = bpy.props.StringProperty(
        name="New Preset",
        default='')
    marker_deselect = bpy.props.BoolProperty(
        name="Deselect New Markers",
        default=True)

    zoom_size = bpy.props.IntProperty(
        name='Zoom Amount',
        default=200,
        min=1,
        description="Zoom size in frames",
        update=zoom_cursor)
    step = bpy.props.IntProperty(
        name="Frame Step",
        default=0,
        min=-7,
        max=7)
    skip_index = bpy.props.IntProperty(
        default=0)

    current_tag = bpy.props.StringProperty(
        name="New Tag",
        default='')
    tags = bpy.props.CollectionProperty(type=VSEQFTags)
    selected_tags = bpy.props.CollectionProperty(type=VSEQFTags)
    show_selected_tags = bpy.props.BoolProperty(
        name="Show Tags For All Selected Sequences",
        default=False)

    quickcuts_insert = bpy.props.IntProperty(
        name="Frames To Insert",
        default=0,
        min=0)
    quickcuts_all = bpy.props.BoolProperty(
        name='Cut All Sequences',
        default=False,
        description='Cut all sequences, regardless of selection (not including locked sequences)')
    snap_new_end = bpy.props.BoolProperty(
        name='Snap Cursor To End Of New Sequences',
        default=False)
    snap_cursor_to_edge = bpy.props.BoolProperty(
        name='Snap Cursor When Dragging Edges',
        default=True)


class VSEQuickFunctionSettings(bpy.types.AddonPreferences):
    """Addon preferences for QuickFunctions, used to enable and disable features"""
    bl_idname = __name__
    parenting = bpy.props.BoolProperty(
        name="Enable Quick Parenting",
        default=True)
    fades = bpy.props.BoolProperty(
        name="Enable Quick Fades",
        default=True)
    list = bpy.props.BoolProperty(
        name="Enable Quick List",
        default=False)
    proxy = bpy.props.BoolProperty(
        name="Enable Quick Proxy",
        default=True)
    markers = bpy.props.BoolProperty(
        name="Enable Quick Markers",
        default=True)
    batch = bpy.props.BoolProperty(
        name="Enable Quick Batch Render",
        default=False)
    tags = bpy.props.BoolProperty(
        name="Enable Quick Tags",
        default=True)
    cuts = bpy.props.BoolProperty(
        name="Enable Quick Cuts",
        default=True)
    edit = bpy.props.BoolProperty(
        name="Enable Compact Edit Panel",
        default=False)
    threepoint = bpy.props.BoolProperty(
        name="Enable Quick Three Point",
        default=True)

    def draw(self, context):
        del context
        layout = self.layout
        layout.prop(self, "parenting")
        layout.prop(self, "fades")
        layout.prop(self, "list")
        layout.prop(self, "proxy")
        layout.prop(self, "markers")
        layout.prop(self, "batch")
        layout.prop(self, "tags")
        layout.prop(self, "cuts")
        layout.prop(self, "edit")
        layout.prop(self, "threepoint")


class VSEQFTempSettings(object):
    """Substitute for the addon preferences when this script isn't loaded as an addon"""
    parenting = bpy.props.BoolProperty(
        name="Enable Quick Parenting",
        default=True)
    fades = bpy.props.BoolProperty(
        name="Enable Quick Fades",
        default=True)
    list = bpy.props.BoolProperty(
        name="Enable Quick List",
        default=True)
    proxy = bpy.props.BoolProperty(
        name="Enable Quick Proxy",
        default=True)
    markers = bpy.props.BoolProperty(
        name="Enable Quick Markers",
        default=True)
    batch = bpy.props.BoolProperty(
        name="Enable Quick Batch Render",
        default=True)
    tags = bpy.props.BoolProperty(
        name="Enable Quick Tags",
        default=True)
    cuts = bpy.props.BoolProperty(
        name="Enable Quick Cuts",
        default=True)
    edit = bpy.props.BoolProperty(
        name="Enable Compact Edit Panel",
        default=True)
    threepoint = bpy.props.BoolProperty(
        name="Enable Quick Three Point",
        default=True)


#Replaced Blender Menus
class VSEQFDeleteConfirm(bpy.types.Menu):
    bl_idname = "vseqf.delete_menu"
    bl_label = "Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete')


class VSEQFDeleteRippleConfirm(bpy.types.Menu):
    bl_idname = "vseqf.delete_ripple_menu"
    bl_label = "Ripple Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete').ripple = True


class SEQUENCER_MT_strip(bpy.types.Menu):
    bl_label = "Strip"

    def draw(self, context):
        vseqf = context.scene.vseqf
        layout = self.layout

        layout.operator_context = 'INVOKE_REGION_WIN'
        layout.operator("vseqf.grab", text="Grab/Move")
        if not vseqf.simplify_menus:
            layout.operator("vseqf.grab", text="Grab/Extend from frame").mode = 'TIME_EXTEND'
            layout.operator("sequencer.gap_remove").all = False
            layout.operator("sequencer.gap_insert")

        layout.separator()

        layout.operator("vseqf.cut", text="Cut (hard) at frame").type = 'HARD'
        layout.operator("vseqf.cut", text="Cut (soft) at frame").type = 'SOFT'
        layout.operator("vseqf.grab", text="Slip Strip Contents").mode = 'SLIP'
        if not vseqf.simplify_menus:
            layout.operator("sequencer.images_separate")
        layout.operator("sequencer.offset_clear")
        if not vseqf.simplify_menus:
            layout.operator("sequencer.deinterlace_selected_movies")
        layout.operator("sequencer.rebuild_proxy")
        layout.separator()

        layout.operator("sequencer.duplicate_move")
        layout.operator("sequencer.delete")

        strip = current_active(context)

        if strip:
            stype = strip.type

            # XXX note strip.type is never equal to 'EFFECT', look at seq_type_items within rna_sequencer.c
            if stype == 'EFFECT':
                pass
            elif stype == 'IMAGE':
                layout.separator()
                layout.operator("sequencer.rendersize")
            elif stype == 'SCENE':
                pass
            elif stype == 'MOVIE':
                layout.separator()
                layout.operator("sequencer.rendersize")
            elif stype == 'SOUND':
                layout.separator()
                layout.operator("sequencer.crossfade_sounds")

        layout.separator()
        layout.operator("vseqf.meta_make")
        layout.operator("sequencer.meta_separate")

        layout.separator()
        layout.operator("sequencer.reload", text="Reload Strips")
        layout.operator("sequencer.reload", text="Reload Strips and Adjust Length").adjust_length = True
        layout.operator("sequencer.reassign_inputs")
        layout.operator("sequencer.swap_inputs")

        layout.separator()
        layout.operator("sequencer.lock")
        layout.operator("sequencer.unlock")
        layout.operator("sequencer.mute").unselected = False
        layout.operator("sequencer.unmute").unselected = False

        layout.operator("sequencer.mute", text="Mute Deselected Strips").unselected = True

        #layout.operator('vseqf.quicksnaps', text='Snap Cursor To Nearest Second').type = 'cursor_to_seconds'
        try:
            #Display only if active sequence is set
            sequence = current_active(context)
            if sequence:
                layout.separator()
                #layout.operator('vseqf.quicksnaps', text='Snap Cursor To Beginning Of Sequence').type = 'cursor_to_beginning'
                #layout.operator('vseqf.quicksnaps', text='Snap Cursor To End Of Sequence').type = 'cursor_to_end'
                layout.operator('vseqf.quicksnaps', text='Snap Sequence Beginning To Cursor').type = 'begin_to_cursor'
                layout.operator('vseqf.quicksnaps', text='Snap Sequence End To Cursor').type = 'end_to_cursor'
                layout.operator('vseqf.quicksnaps', text='Snap Sequence To Previous Sequence').type = 'sequence_to_previous'
                layout.operator('vseqf.quicksnaps', text='Snap Sequence To Next Sequence').type = 'sequence_to_next'
        except:
            pass
        if not vseqf.simplify_menus:
            layout.operator_menu_enum("sequencer.swap", "side")

            layout.separator()

            layout.operator("sequencer.swap_data")
            layout.menu("SEQUENCER_MT_change")


class SEQUENCER_MT_add(bpy.types.Menu):
    bl_label = "Add"

    def draw(self, context):
        del context
        layout = self.layout

        layout.operator_context = 'INVOKE_REGION_WIN'

        if len(bpy.data.scenes) > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.scene_strip_add", text="Scene...")
        else:
            layout.operator_menu_enum("sequencer.scene_strip_add", "scene", text="Scene")

        if len(bpy.data.movieclips) > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.movieclip_strip_add", text="Clips...")
        else:
            layout.operator_menu_enum("sequencer.movieclip_strip_add", "clip", text="Clip")

        if len(bpy.data.masks) > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.mask_strip_add", text="Masks...")
        else:
            layout.operator_menu_enum("sequencer.mask_strip_add", "mask", text="Mask")

        layout.operator("vseqf.import", text="Movie").type = 'MOVIE'
        layout.operator("vseqf.import", text="Image").type = 'IMAGE'
        layout.operator("sequencer.sound_strip_add", text="Sound")

        layout.menu("SEQUENCER_MT_add_effect")


#Register properties, operators, menus and shortcuts
classes = (SEQUENCER_MT_add, SEQUENCER_MT_strip, VSEQFAddZoom, VSEQFClearZooms, VSEQFCompactEdit, VSEQFContextCursor,
           VSEQFContextMarker, VSEQFContextNone, VSEQFContextSequence, VSEQFContextSequenceLeft,
           VSEQFContextSequenceRight, VSEQFCut, VSEQFDelete, VSEQFDeleteConfirm, VSEQFDeleteRippleConfirm,
           VSEQFFollow, VSEQFGrab, VSEQFGrabAdd, VSEQFImport, VSEQFMarkerPreset, VSEQFMeta, VSEQFQuickBatchRender,
           VSEQFQuickBatchRenderPanel, VSEQFQuickCutsMenu, VSEQFQuickCutsPanel, VSEQFQuickFadesClear,
           VSEQFQuickFadesCross, VSEQFQuickFadesMenu, VSEQFQuickFadesPanel, VSEQFQuickFadesSet, VSEQFQuickListDown,
           VSEQFQuickListPanel, VSEQFQuickListSelect, VSEQFQuickListUp, VSEQFQuickMarkerDelete, VSEQFQuickMarkerJump,
           VSEQFQuickMarkerList, VSEQFQuickMarkerMove, VSEQFQuickMarkerPresetList, VSEQFQuickMarkerRename,
           VSEQFQuickMarkersAddPreset, VSEQFQuickMarkersMenu, VSEQFQuickMarkersPanel, VSEQFQuickMarkersPlace,
           VSEQFQuickMarkersRemovePreset, VSEQFQuickParents, VSEQFQuickParentsClear, VSEQFQuickParentsMenu,
           VSEQFQuickSnaps, VSEQFQuickSnapsMenu, VSEQFQuickTagList, VSEQFQuickTagListAll, VSEQFQuickTagsAdd,
           VSEQFQuickTagsClear, VSEQFQuickTagsMenu, VSEQFQuickTagsPanel, VSEQFQuickTagsRemove, VSEQFQuickTagsRemoveFrom,
           VSEQFQuickTagsSelect, VSEQFQuickTimeline, VSEQFQuickTimelineMenu, VSEQFQuickZoomPreset,
           VSEQFQuickZoomPresetMenu, VSEQFQuickZooms, VSEQFQuickZoomsMenu, VSEQFRemoveZoom, VSEQFSelectGrab,
           VSEQFSettingsMenu, VSEQFTags, VSEQFThreePointBrowserPanel, VSEQFThreePointImport,
           VSEQFThreePointImportToClip, VSEQFThreePointOperator, VSEQFThreePointPanel, VSEQFZoomPreset,
           VSEQFQuickShortcutsNudge, VSEQFQuickShortcutsSpeed, VSEQFQuickShortcutsSkip, VSEQFQuickShortcutsResetPlay,
           VSEQFQuick3PointValues, VSEQFSetting)


def register():
    bpy.utils.register_class(VSEQuickFunctionSettings)

    #Register classes
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.SEQUENCER_PT_edit.append(edit_panel)
    global vseqf_draw_handler
    if vseqf_draw_handler:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(vseqf_draw_handler, 'WINDOW')
    vseqf_draw_handler = bpy.types.SpaceSequenceEditor.draw_handler_add(vseqf_draw, (), 'WINDOW', 'POST_PIXEL')

    #Add menus
    bpy.types.SEQUENCER_HT_header.append(draw_quickspeed_header)
    bpy.types.SEQUENCER_HT_header.append(draw_follow_header)
    bpy.types.SEQUENCER_MT_view.append(draw_quickzoom_menu)
    bpy.types.SEQUENCER_MT_view.prepend(draw_quicksettings_menu)
    bpy.types.SEQUENCER_MT_marker.prepend(draw_quickmarker_menu)

    #New variables
    bpy.types.Scene.vseqf_skip_interval = bpy.props.IntProperty(default=0, min=0)
    bpy.types.Sequence.parent = bpy.props.StringProperty()
    bpy.types.Sequence.tags = bpy.props.CollectionProperty(type=VSEQFTags)
    bpy.types.Scene.vseqf = bpy.props.PointerProperty(type=VSEQFSetting)
    bpy.types.MovieClip.import_settings = bpy.props.PointerProperty(type=VSEQFQuick3PointValues)
    bpy.types.Sequence.new = bpy.props.BoolProperty(default=True)
    bpy.types.Sequence.last_name = bpy.props.StringProperty()

    #Register shortcuts
    keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Sequencer', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
    keymapitems = keymap.keymap_items

    for keymapitem in keymapitems:
        #Iterate through keymaps and delete old shortcuts
        if (keymapitem.type == 'Z') | (keymapitem.type == 'F') | (keymapitem.type == 'S') | (keymapitem.type == 'G') | (keymapitem.type == 'RIGHTMOUSE') | (keymapitem.type == 'K') | (keymapitem.type == 'E') | (keymapitem.type == 'X') | (keymapitem.type == 'DEL') | (keymapitem.type == 'M'):
            keymapitems.remove(keymapitem)
    keymapmarker = keymapitems.new('wm.call_menu', 'M', 'PRESS', alt=True)
    keymapmarker.properties.name = 'vseqf.quickmarkers_menu'
    keymapitems.new('vseqf.meta_make', 'G', 'PRESS', ctrl=True)
    keymapzoom = keymapitems.new('wm.call_menu', 'Z', 'PRESS')
    keymapzoom.properties.name = 'vseqf.quickzooms_menu'
    keymapfade = keymapitems.new('wm.call_menu', 'F', 'PRESS')
    keymapfade.properties.name = 'vseqf.quickfades_menu'
    keymapsnap = keymapitems.new('wm.call_menu', 'S', 'PRESS')
    keymapsnapto = keymapitems.new('vseqf.quicksnaps', 'S', 'PRESS', shift=True)
    keymapsnapto.properties.type = 'selection_to_cursor'
    keymapsnap.properties.name = 'vseqf.quicksnaps_menu'
    keymapparent = keymapitems.new('wm.call_menu', 'P', 'PRESS', ctrl=True)
    keymapparent.properties.name = 'vseqf.quickparents_menu'
    keymapparentselect = keymapitems.new('vseqf.quickparents', 'P', 'PRESS', shift=True)
    keymapparentselect.properties.action = 'select_children'
    keymapcuts = keymapitems.new('wm.call_menu', 'K', 'PRESS', ctrl=True)
    keymapcuts.properties.name = 'vseqf.quickcuts_menu'
    keymapitems.new('vseqf.cut', 'K', 'PRESS')
    keymapcuthard = keymapitems.new('vseqf.cut', 'K', 'PRESS', shift=True)
    keymapcuthard.properties.type = 'HARD'
    keymapcutripple = keymapitems.new('vseqf.cut', 'K', 'PRESS', alt=True)
    keymapcutripple.properties.type = 'RIPPLE'
    keymapitems.new('vseqf.grab', 'G', 'PRESS')
    keymapitems.new('vseqf.select_grab', 'RIGHTMOUSE', 'PRESS')
    keymapgrabextend = keymapitems.new('vseqf.grab', 'E', 'PRESS')
    keymapgrabextend.properties.mode = 'TIME_EXTEND'
    keymapslip = keymapitems.new('vseqf.grab', 'S', 'PRESS', alt=True)
    keymapslip.properties.mode = 'SLIP'
    keymapdelete1 = keymapitems.new('wm.call_menu', 'X', 'PRESS')
    keymapdelete1.properties.name = 'vseqf.delete_menu'
    keymapdelete2 = keymapitems.new('wm.call_menu', 'DEL', 'PRESS')
    keymapdelete2.properties.name = 'vseqf.delete_menu'
    keymapdelete3 = keymapitems.new('wm.call_menu', 'X', 'PRESS', alt=True)
    keymapdelete3.properties.name = 'vseqf.delete_ripple_menu'
    keymapdelete4 = keymapitems.new('wm.call_menu', 'DEL', 'PRESS', alt=True)
    keymapdelete4.properties.name = 'vseqf.delete_ripple_menu'

    #QuickShortcuts Shortcuts
    keymapitems.new('vseqf.cut', 'NUMPAD_0', 'PRESS')
    keymapitem = keymapitems.new('vseqf.cut', 'NUMPAD_0', 'PRESS', alt=True)
    keymapitem.properties.type = 'RIPPLE'

    #Numpad: basic movement and playback
    keymapitem = keymapitems.new('screen.frame_offset', 'NUMPAD_1', 'PRESS')
    keymapitem.properties.delta = -1
    keymapitem = keymapitems.new('screen.frame_offset', 'NUMPAD_3', 'PRESS')
    keymapitem.properties.delta = 1
    keymapitem = keymapitems.new('vseqf.change_speed', 'NUMPAD_4', 'PRESS')
    keymapitem.properties.speed_change = 'DOWN'
    keymapitem = keymapitems.new('vseqf.change_speed', 'NUMPAD_6', 'PRESS')
    keymapitem.properties.speed_change = 'UP'
    keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_7', 'PRESS')
    keymapitem.properties.type = 'LASTSECOND'
    keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_9', 'PRESS')
    keymapitem.properties.type = 'NEXTSECOND'
    keymapitems.new('vseqf.reset_playback', 'NUMPAD_5', 'PRESS')

    #Numpad + Ctrl: Advanced movement/jumps
    keymapitem = keymapitems.new('screen.keyframe_jump', 'NUMPAD_1', 'PRESS', ctrl=True)
    keymapitem.properties.next = False
    keymapitem = keymapitems.new('screen.keyframe_jump', 'NUMPAD_3', 'PRESS', ctrl=True)
    keymapitem.properties.next = True
    keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_4', 'PRESS', ctrl=True)
    keymapitem.properties.type = 'LASTEDGE'
    keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_6', 'PRESS', ctrl=True)
    keymapitem.properties.type = 'NEXTEDGE'
    keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_7', 'PRESS', ctrl=True)
    keymapitem.properties.type = 'LASTMARKER'
    keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_9', 'PRESS', ctrl=True)
    keymapitem.properties.type = 'NEXTMARKER'

    #Numpad + Alt: Move selected strips
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_1', 'PRESS', alt=True)
    keymapitem.properties.direction = 'LEFT'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_3', 'PRESS', alt=True)
    keymapitem.properties.direction = 'RIGHT'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_4', 'PRESS', alt=True)
    keymapitem.properties.direction = 'LEFT-M'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_6', 'PRESS', alt=True)
    keymapitem.properties.direction = 'RIGHT-M'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_7', 'PRESS', alt=True)
    keymapitem.properties.direction = 'LEFT-L'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_9', 'PRESS', alt=True)
    keymapitem.properties.direction = 'RIGHT-L'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_2', 'PRESS', alt=True)
    keymapitem.properties.direction = 'DOWN'
    keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_8', 'PRESS', alt=True)
    keymapitem.properties.direction = 'UP'
    keymapitems.new('vseqf.grab', 'NUMPAD_5', 'PRESS', alt=True)

    #Numpad + Shift: Zoom viewport
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_1', 'PRESS', shift=True)
    keymapitem.properties.area = '2'
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_2', 'PRESS', shift=True)
    keymapitem.properties.area = '10'
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_3', 'PRESS', shift=True)
    keymapitem.properties.area = '30'
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_4', 'PRESS', shift=True)
    keymapitem.properties.area = '60'
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_5', 'PRESS', shift=True)
    keymapitem.properties.area = '120'
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_6', 'PRESS', shift=True)
    keymapitem.properties.area = '300'
    keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_7', 'PRESS', shift=True)
    keymapitem.properties.area = '600'
    keymapitems.new('sequencer.view_selected', 'NUMPAD_8', 'PRESS', shift=True)
    keymapitems.new('sequencer.view_all', 'NUMPAD_9', 'PRESS', shift=True)

    #Register handler
    handlers = bpy.app.handlers.frame_change_post
    for handler in handlers:
        if " frame_step " in str(handler):
            handlers.remove(handler)
    handlers.append(frame_step)
    handlers = bpy.app.handlers.scene_update_post
    for handler in handlers:
        if " vseqf_continuous " in str(handler):
            handlers.remove(handler)
    handlers.append(vseqf_continuous)


def unregister():
    global vseqf_draw_handler
    bpy.types.SpaceSequenceEditor.draw_handler_remove(vseqf_draw_handler, 'WINDOW')

    #Unregister menus
    bpy.types.SEQUENCER_HT_header.remove(draw_quickspeed_header)
    bpy.types.SEQUENCER_MT_view.remove(draw_quickzoom_menu)
    bpy.types.SEQUENCER_MT_view.remove(draw_quicksettings_menu)
    bpy.types.SEQUENCER_HT_header.remove(draw_follow_header)
    bpy.types.SEQUENCER_PT_edit.remove(edit_panel)

    #Remove shortcuts
    keymapitems = bpy.context.window_manager.keyconfigs.addon.keymaps['Sequencer'].keymap_items
    for keymapitem in keymapitems:
        if (keymapitem.type == 'Z') | (keymapitem.type == 'F') | (keymapitem.type == 'S') | (keymapitem.type == 'G') | (keymapitem.type == 'RIGHTMOUSE') | (keymapitem.type == 'K') | (keymapitem.type == 'E') | (keymapitem.type == 'X') | (keymapitem.type == 'DEL') | (keymapitem.type == 'M') | (keymapitem.type == 'NUMPAD_0') | (keymapitem.type == 'NUMPAD_1') | (keymapitem.type == 'NUMPAD_2') | (keymapitem.type == 'NUMPAD_3') | (keymapitem.type == 'NUMPAD_4') | (keymapitem.type == 'NUMPAD_5') | (keymapitem.type == 'NUMPAD_6') | (keymapitem.type == 'NUMPAD_7') | (keymapitem.type == 'NUMPAD_8') | (keymapitem.type == 'NUMPAD_9'):
            keymapitems.remove(keymapitem)

    #Remove handlers for modal operators
    handlers = bpy.app.handlers.frame_change_post
    for handler in handlers:
        if " frame_step " in str(handler):
            handlers.remove(handler)
    handlers = bpy.app.handlers.scene_update_post
    for handler in handlers:
        if " vseqf_continuous " in str(handler):
            handlers.remove(handler)
    try:
        bpy.utils.unregister_class(VSEQuickFunctionSettings)
    except RuntimeError:
        pass

    #Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
