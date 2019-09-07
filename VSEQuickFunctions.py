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
Known Issues:
    Ending cursor following causes inputs to not work until left mouse is clicked... sometimes??
    Quick 3point causes recursion errors sometimes when adjusting in/out
    Uncut does not work on movieclip type sequences... there appears to be no way of getting the sequence's source file.
    Right now the script cannot apply a vertical zoom level, as far as I can tell this is missing functionality in Blender's python api.

Future Possibilities:
    Add grab mode options for marker moving (press m while grabbing to change, show real-time updates of position)
    Remove multiple drag feature (Apparently it will be implemented in blender at some point?)
    Add special tags with time index and length, displayed in overlay as clip markers - need to implement display, and interface in panel
    Ripple insert in real-time while grabbing... need to think about how to do this, but I want it!
    Ability to ripple cut beyond the edge of the selected strips to ADD to the clip
    Copy/paste wrapper that copies strip animation data
    Showing a visual offset on the active audio sequence, showing how far out of sync it is from it's video parent

Todo:
    Once the tools panel is implemented in sequencer, rework all panels and menus to make better use of it.

Changelog:
0.94
    Frame skipping now works with reverse playback as well, and fixed poor behavior
    Added QuickShortcuts - timeline and sequence movement using the numpad.  Thanks to tintwotin for the ideas!
    Added option to snap cursor to a dragged edge if one edge is grabbed, if two are grabbed, the second edge will be set to the overlay frame.
    Many improvements to Quick3Point interface
    Fixed a bug that would cause slipped sequences to jump around
    Split Quick Batch Render off into its own addon
    Fixed bug where adjusting the left edge of single images would cause odd behavior
    Significant improvements to cursor following
    Improvements to ripple behavior, fixed bugs relating to it as well
    Improved marker grabbing behavior
    Improvements to Quick3Point
    Added display of current strip length under center of strip
    Fixed canceled grabs causing waveforms to redraw
    Improved QuickTags interface
    Reworked ripple delete, it should now behave properly with overlapping sequences

0.95
    Updated for Blender 2.8 - lots of code changes, lots of bug fixes, updated menus, updated panels
    Disabled ripple and edge snap while in slip mode
    Various optimizations to ripple and grabbing
    Added support for left and right click mouse moves
    Updated frame skipping to work with new limitations in Blender
    Added a modal fade operator for easily setting/changing fades, moved fades menu to shift-f
    Strip information is now drawn for all selected strips, not just active

0.96 (in progress)
    Fixed bug where box select wouldn't work.
    Removed right-click hold menus - too buggy and blocked box select.  New context menu shortcut: '`'
    Improved frame skipping
    Fixed bug where cut strips with deleted parents could have their old parent 'replaced' by a new cut
    Fixed bug in fade operator where waveforms for strips with no animation data would vanish
    Removed QuickList
    Fixed a bug where clearing fades could cause an error - thanks jaggz
    Improved fades - should be better about maintaining the original curve, and not leave extra points when fades are cleared

"""

import bpy
import bgl
import gpu
import blf
import math
import os
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ImportHelper
from gpu_extras.batch import batch_for_shader


bl_info = {
    "name": "VSE Quick Functions",
    "description": "Improves functionality of the sequencer by adding new menus and functions for snapping, adding fades, zooming, sequence parenting, ripple editing, playback speed, and more.",
    "author": "Hudson Barkley (Snu/snuq/Aritodo)",
    "version": (0, 9, 5),
    "blender": (2, 80, 0),
    "location": "Sequencer Panels; Sequencer Menus; Sequencer S, F, Shift-F, Z, Ctrl-P, Shift-P, Alt-M, Alt-K Shortcuts",
    "wiki_url": "https://github.com/snuq/VSEQF",
    "tracker_url": "https://github.com/snuq/VSEQF/issues",
    "category": "Sequencer"
}
vseqf_draw_handler = None
right_click_time = 0.5
marker_area_height = 40
marker_grab_distance = 100


#Miscellaneous Functions
def get_fps(scene=None):
    if scene is None:
        scene = bpy.context.scene
    return scene.render.fps / scene.render.fps_base


def add_to_value(value, character, is_float=True):
    if character in ['ZERO', 'NUMPAD_0']:
        value = value + '0'
    elif character in ['ONE', 'NUMPAD_1']:
        value = value + '1'
    elif character in ['TWO', 'NUMPAD_2']:
        value = value + '2'
    elif character in ['THREE', 'NUMPAD_3']:
        value = value + '3'
    elif character in ['FOUR', 'NUMPAD_4']:
        value = value + '4'
    elif character in ['FIVE', 'NUMPAD_5']:
        value = value + '5'
    elif character in ['SIX', 'NUMPAD_6']:
        value = value + '6'
    elif character in ['SEVEN', 'NUMPAD_7']:
        value = value + '7'
    elif character in ['EIGHT', 'NUMPAD_8']:
        value = value + '8'
    elif character in ['NINE', 'NUMPAD_9']:
        value = value + '9'
    elif character in ['PERIOD', 'NUMPAD_PERIOD']:
        if '.' not in value and is_float:
            value = value + '.'
    elif character in ['MINUS', 'NUMPAD_MINUS']:
        if '-' in value:
            value = value[1:]
        else:
            value = '-' + value
    elif character == 'BACK_SPACE':
        value = value[:-1]
    return value


def near_marker(context, frame):
    if context.scene.timeline_markers:
        markers = sorted(context.scene.timeline_markers, key=lambda x: abs(x.frame - frame))
        marker = markers[0]
        if abs(marker.frame - frame) <= marker_grab_distance:
            return marker
    return None


def on_sequence(frame, channel, sequence):
    if frame >= sequence.frame_final_start and frame <= sequence.frame_final_end and int(channel) == sequence.channel:
        return True
    else:
        return False


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


def ripple_timeline(sequences, start_frame, ripple_amount, select_ripple=True):
    """Moves all given sequences starting after the frame given as 'start_frame', by moving them forward by 'ripple_amount' frames.
    'select_ripple' will select all sequences that were moved."""

    to_change = []
    for sequence in sequences:
        if sequence.frame_final_end > start_frame - ripple_amount and sequence.frame_final_start > start_frame:
            to_change.append([sequence, sequence.channel, sequence.frame_start + ripple_amount, True])
    for seq in to_change:
        sequence = seq[0]
        sequence.channel = seq[1]
        if not hasattr(sequence, 'input_1'):
            sequence.frame_start = seq[2]
        if select_ripple:
            sequence.select = True
        if (sequence.frame_start != seq[2] or sequence.channel != seq[1]) and seq[3]:
            seq[3] = False
            to_change.append(seq)


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


def find_timeline_height(sequences):
    height = 1
    for sequence in sequences:
        if sequence.channel > height:
            height = sequence.channel
    return height


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
    if __name__ in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons[__name__].preferences
    else:
        prefs = VSEQFTempSettings()
    return prefs


def draw_line(sx, sy, ex, ey, color=(1.0, 1.0, 1.0, 1.0)):
    coords = [(sx, sy), (ex, ey)]
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {'pos': coords})
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_rect(x, y, w, h, color=(1.0, 1.0, 1.0, 1.0)):
    vertices = ((x, y), (x+w, y), (x, y+h), (x+w, y+h))
    indices = ((0, 1, 2), (2, 1, 3))
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_tri(v1, v2, v3, color=(1.0, 1.0, 1.0, 1.0)):
    vertices = (v1, v2, v3)
    indices = ((0, 1, 2), )
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_text(x, y, size, text, justify='left', color=(1.0, 1.0, 1.0, 1.0)):
    #Draws basic text at a given location
    font_id = 0
    blf.color(font_id, *color)
    if justify == 'right':
        text_width, text_height = blf.dimensions(font_id, text)
    else:
        text_width = 0
    blf.position(font_id, x - text_width, y, 0)
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


def draw_quicksettings_menu(self, context):
    """Draws the general settings menu for QuickContinuous related functions"""

    del context
    layout = self.layout
    layout.menu('VSEQF_MT_settings_menu', text="Quick Functions Settings")


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
            'nooverlap': Returns the previous sequence, ignoring any that are overlapping
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
            elif mode == 'channel' or mode == 'nooverlap':
                if len(nexts) > 0:
                    found = min(nexts, key=lambda next_seq: (next_seq.frame_final_start - selected_sequence.frame_final_end))
            else:
                if len(nexts_all) > 0:
                    found = min(nexts_all, key=lambda next_seq: (next_seq.frame_final_start - selected_sequence.frame_final_end))
        else:
            if mode == 'overlap':
                if len(overlap_previous) > 0:
                    found = min(overlap_previous, key=lambda overlap: abs(overlap.channel - selected_sequence.channel))
            elif mode == 'channel' or mode == 'nooverlap':
                if len(previous) > 0:
                    found = min(previous, key=lambda prev: (selected_sequence.frame_final_start - prev.frame_final_end))
            else:
                if len(previous_all) > 0:
                    found = min(previous_all, key=lambda prev: (selected_sequence.frame_final_start - prev.frame_final_end))
    return found


def timecode_from_frames(frame, fps, levels=0, subsecond_type='miliseconds', mode='string'):
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
        mode: return mode, if 'string', will return a string timecode, if other, will return a list of integers

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

    if mode != 'string':
        return [hours, minutes, seconds, subseconds]
    else:
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


class VSEQF_PT_CompactEdit(bpy.types.Panel):
    """Panel for displaying QuickList"""
    bl_label = "Edit Strip Compact"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()

        if not current_active(context):
            return False
        else:
            return prefs.edit

    def draw(self, context):
        prefs = get_prefs()
        scene = context.scene
        strip = current_active(context)
        vseqf = scene.vseqf
        layout = self.layout
        fps = get_fps(scene)

        row = layout.row()
        split = row.split(factor=.8)
        split.prop(strip, 'name', text="")
        split.label(text="("+strip.type+")")

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
            split = sub.split(factor=.3, align=True)
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
            fade_curve = get_fade_curve(context, strip, create=False)
            if fade_curve:
                fadein = fades(fade_curve, strip, 'detect', 'in')
                fadeout = fades(fade_curve, strip, 'detect', 'out')
            else:
                fadein = 0
                fadeout = 0

            row = layout.row()
            if fadein > 0:
                row.label(text="Fadein: "+str(round(fadein))+" Frames")
            else:
                row.label(text="No Fadein Detected")
            if fadeout > 0:
                row.label(text="Fadeout: "+str(round(fadeout))+" Frames")
            else:
                row.label(text="No Fadeout Detected")

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
                split = row.split(factor=.8, align=True)
                split.label(text="Parent: "+parent.name)
                split.operator('vseqf.quickparents', text='', icon="ARROW_LEFTRIGHT").action = 'select_parent'
                split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_parent'
            if len(children) > 0:
                row = box.row()
                split = row.split(factor=.8, align=True)
                subsplit = split.split(factor=.1)
                subsplit.prop(vseqf, 'expanded_children', icon="TRIA_DOWN" if scene.vseqf.expanded_children else "TRIA_RIGHT", icon_only=True, emboss=False)
                subsplit.label(text="Children: "+children[0].name)
                split.operator('vseqf.quickparents', text='', icon="ARROW_LEFTRIGHT").action = 'select_children'
                split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_children'
                if vseqf.expanded_children:
                    index = 1
                    while index < len(children):
                        row = box.row()
                        split = row.split(factor=.1)
                        split.label(text='')
                        split.label(text=children[index].name)
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


class VSEQFMetaExit(bpy.types.Operator):
    bl_idname = 'vseqf.meta_exit'
    bl_label = 'Exit The Current Meta Strip'

    def execute(self, context):
        del context
        if inside_meta_strip():
            bpy.ops.sequencer.select_all(action='DESELECT')
            bpy.ops.sequencer.meta_toggle()
        return{'FINISHED'}


class VSEQF_PT_Parenting(bpy.types.Panel):
    bl_label = 'Parenting'
    bl_parent_id = "SEQUENCER_PT_adjust"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
        if prefs.fades:
            active_sequence = current_active(context)
            if active_sequence:
                return True
        return False

    def draw(self, context):
        #display info about parenting relationships
        sequences = current_sequences(context)
        active_sequence = current_active(context)
        scene = context.scene
        layout = self.layout

        children = find_children(active_sequence, sequences=sequences)
        parent = find_parent(active_sequence)

        row = layout.row()
        row.operator('vseqf.quickparents', text='Set Active As Parent').action = 'add'

        #List relationships for active sequence
        if parent:
            box = layout.box()
            row = box.row()
            row.label(text="Parent: ")
            row.label(text=parent.name)
            row = box.row()
            row.operator('vseqf.quickparents', text='Select Parent').action = 'select_parent'
            row.operator('vseqf.quickparents', text='Remove Parent', icon="X").action = 'clear_parent'
        if len(children) > 0:
            box = layout.box()
            for index, child in enumerate(children):
                row = box.row()
                if index == 0:
                    row.label(text='Children:')
                else:
                    row.label(text='')
                row.label(text=child.name)
            row = box.row()
            row.operator('vseqf.quickparents', text='Select Children').action = 'select_children'
            row.operator('vseqf.quickparents', text='Remove Children', icon="X").action = 'clear_children'


#Functions related to continuous update
@persistent
def vseqf_continuous(scene):
    if not bpy.context.scene or bpy.context.scene != scene:
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
    context = bpy.context
    prefs = get_prefs()
    colors = bpy.context.preferences.themes[0].user_interface
    text_color = list(colors.wcol_text.text_sel)+[1]
    active_strip = current_active(context)
    if not active_strip:
        return
    region = bpy.context.region
    view = region.view2d

    #determine pixels per frame and channel
    width = region.width
    height = region.height
    left, bottom = view.region_to_view(0, 0)
    right, top = view.region_to_view(width, height)
    if math.isnan(left):
        return
    shown_width = right - left
    shown_height = top - bottom
    channel_px = height / shown_height
    frame_px = width / shown_width

    min_x = 25
    max_x = width - 10
    fps = get_fps()
    draw_strip_info(context, active_strip, fps, frame_px, channel_px, min_x, max_x, view, width, text_color, prefs.fades, prefs.parenting, True)
    selected = current_selected(context)
    for strip in selected:
        if strip != active_strip:
            draw_strip_info(context, strip, fps, frame_px, channel_px, min_x, max_x, view, width, text_color, prefs.fades, prefs.parenting, False)


def draw_strip_info(context, active_strip, fps, frame_px, channel_px, min_x, max_x, view, width, text_color, show_fades, show_parenting, show_length):
    length = active_strip.frame_final_duration
    active_x = active_strip.frame_final_start + (length / 2)
    active_y = active_strip.channel + 0.5
    active_left, active_top = view.view_to_region(active_strip.frame_final_start, active_strip.channel+1, clip=False)
    active_right, active_bottom = view.view_to_region(active_strip.frame_final_end, active_strip.channel, clip=False)
    active_pos_x, active_pos_y = view.view_to_region(active_x, active_strip.channel + 0.5, clip=False)
    active_width = length * frame_px
    fade_height = channel_px / 20
    text_size = 10
    strip_x = active_pos_x
    if strip_x <= min_x and active_right > min_x:
        strip_x = min_x
    if strip_x >= max_x and active_left < max_x:
        strip_x = max_x

    #display length
    if show_length:
        length_timecode = timecode_from_frames(length, fps)
        draw_text(strip_x - (strip_x / width) * 40, active_bottom + (channel_px * .1), text_size, '('+length_timecode+')', text_color)

    #display fades
    if show_fades and active_width > text_size * 6:
        fade_curve = get_fade_curve(context, active_strip, create=False)
        if fade_curve:
            fadein = int(fades(fade_curve, active_strip, 'detect', 'in'))
            if fadein and length:
                fadein_percent = fadein / length
                draw_rect(active_left, active_top - (fade_height * 2), fadein_percent * active_width, fade_height, color=(.5, .5, 1, .75))
                draw_text(active_left, active_top, text_size, 'In: '+str(fadein), text_color)
            fadeout = int(fades(fade_curve, active_strip, 'detect', 'out'))
            if fadeout and length:
                fadeout_percent = fadeout / length
                fadeout_width = active_width * fadeout_percent
                draw_rect(active_right - fadeout_width, active_top - (fade_height * 2), fadeout_width, fade_height, color=(.5, .5, 1, .75))
                draw_text(active_right - (text_size * 4), active_top, text_size, 'Out: '+str(fadeout), text_color)
    if show_parenting:
        bgl.glEnable(bgl.GL_BLEND)
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
            draw_line(strip_x, active_pos_y, pixel_x, pixel_y, color=(0.0, 0.0, 0.0, 0.2))
        coords = []
        for child in children:
            child_x = child.frame_final_start + (child.frame_final_duration / 2)
            child_y = child.channel + 0.5
            distance_x = child_x - active_x
            distance_y = child_y - active_y
            pixel_x_distance = int(distance_x * frame_px)
            pixel_y_distance = int(distance_y * channel_px)
            pixel_x = active_pos_x + pixel_x_distance
            pixel_y = active_pos_y + pixel_y_distance
            coords.append((strip_x, active_pos_y))
            coords.append((pixel_x, pixel_y))
        shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {'pos': coords})
        shader.bind()
        shader.uniform_float('color', (1.0, 1.0, 1.0, 0.2))
        batch.draw(shader)
        bgl.glDisable(bgl.GL_BLEND)


#Functions and classes related to QuickShortcuts
def nudge_selected(frame=0, channel=0):
    """Moves the selected sequences by a given amount."""

    to_nudge = []
    for sequence in bpy.context.selected_sequences:
        if vseqf_parenting():
            get_recursive(sequence, to_nudge)
        else:
            to_nudge.append(sequence)
    if channel > 0:
        to_nudge.sort(key=lambda x: x.channel, reverse=True)
    if channel < 0:
        to_nudge.sort(key=lambda x: x.channel)
    for sequence in to_nudge:
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

    direction: bpy.props.EnumProperty(name='Direction', items=[("UP", "Up", "", 1), ("DOWN", "Down", "", 2), ("LEFT", "Left", "", 3), ("RIGHT", "Right", "", 4), ("LEFT-M", "Left Medium", "", 5), ("RIGHT-M", "Right Medium", "", 6), ("LEFT-L", "Left Large", "", 7), ("RIGHT-L", "Right Large", "", 8)])

    def execute(self, context):
        bpy.ops.ed.undo_push()
        second = int(round(get_fps(context.scene)))
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

    speed_change: bpy.props.EnumProperty(name='Type', items=[("UP", "Up", "", 1), ("DOWN", "Down", "", 2)])

    def execute(self, context):
        if self.speed_change == 'UP':
            if not context.screen.is_animation_playing:
                #playback is stopped, start at speed 1
                bpy.ops.screen.animation_play()
                context.scene.vseqf.step = 1
            elif context.scene.vseqf.step == 0:
                bpy.ops.screen.animation_cancel(restore_frame=False)
            elif context.scene.vseqf.step < 4:
                context.scene.vseqf.step = context.scene.vseqf.step + 1
        elif self.speed_change == 'DOWN':
            if not context.screen.is_animation_playing:
                #playback is stopped, start at speed -1
                bpy.ops.screen.animation_play(reverse=True)
                context.scene.vseqf.step = -1
            elif context.scene.vseqf.step == 0:
                bpy.ops.screen.animation_cancel(restore_frame=False)
            elif context.scene.vseqf.step > -4:
                context.scene.vseqf.step = context.scene.vseqf.step - 1
                if context.scene.vseqf.step == 1:
                    bpy.ops.screen.animation_cancel(restore_frame=False)
                    bpy.ops.screen.animation_play()
        if context.screen.is_animation_playing and context.scene.vseqf.step == 0:
            bpy.ops.screen.animation_play()
        return{'FINISHED'}


class VSEQFQuickShortcutsSkip(bpy.types.Operator):
    bl_idname = 'vseqf.skip_timeline'
    bl_label = 'Skip timeline location'

    type: bpy.props.EnumProperty(name='Type', items=[("NEXTSECOND", "One Second Forward", "", 1), ("LASTSECOND", "One Second Backward", "", 2), ("NEXTEDGE", "Next Clip Edge", "", 3), ("LASTEDGE", "Last Clip Edge", "", 4), ("LASTMARKER", "Last Marker", "", 5), ("NEXTMARKER", "Next Marker", "", 6)])

    def execute(self, context):
        bpy.ops.ed.undo_push()
        second_frames = int(round(get_fps(context.scene)))
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

    direction: bpy.props.EnumProperty(name='Direction', items=[("FORWARD", "Forward", "", 1), ("BACKWARD", "Backward", "", 2)])

    def execute(self, context):
        if self.direction == 'BACKWARD':
            context.scene.vseqf.step = -1
            bpy.ops.screen.animation_play(reverse=True)
        else:
            context.scene.vseqf.step = 1
            bpy.ops.screen.animation_play()
        return{'FINISHED'}


#Functions and classes related to threepoint editing
def update_import_frame_in(self, fps):
    self.import_frame_in = (self.import_minutes_in * 60 * fps) + (self.import_seconds_in * fps) + self.import_frames_in


def update_import_frame_length(self, fps):
    self.import_frame_length = (self.import_minutes_length * 60 * fps) + (self.import_seconds_length * fps) + self.import_frames_length


def update_import_minutes_in(self, context):
    fps = get_fps(context.scene)
    length = self.full_length
    length_timecode = timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length > max_minutes:
        if self.import_minutes_length > 0:
            self.import_minutes_length = self.import_minutes_length - 1
        else:
            self.import_minutes_in = self.import_minutes_in - 1
    update_import_frame_in(self, fps)


def update_import_minutes_length(self, context):
    fps = get_fps(context.scene)
    length = self.full_length
    length_timecode = timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length > max_minutes:
        self.import_minutes_length = self.import_minutes_length - 1
    update_import_frame_length(self, fps)


def update_import_seconds_in(self, context):
    fps = get_fps(context.scene)
    length = self.full_length
    length_timecode = timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_seconds_in >= 60 and self.import_minutes_in < max_minutes:
        self.import_seconds_in = 0
        self.import_minutes_in = self.import_minutes_in + 1
    else:
        if self.import_seconds_in + self.import_seconds_length >= 60:
            max_minutes = max_minutes - 1
        if self.import_minutes_in + self.import_minutes_length >= max_minutes:
            if self.import_seconds_length > 0:
                self.import_seconds_length = self.import_seconds_length - 1
            elif self.import_minutes_length > 0:
                self.import_minutes_length = self.import_minutes_length - 1
                self.import_seconds_length = 59
            elif self.import_seconds_in + self.import_seconds_length >= max_seconds:
                self.import_seconds_in = max_seconds
    update_import_frame_in(self, fps)


def update_import_seconds_length(self, context):
    fps = get_fps(context.scene)
    length = self.full_length
    length_timecode = timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length >= max_minutes:
        if self.import_seconds_length + self.import_seconds_in > max_seconds:
            self.import_seconds_length = max_seconds - self.import_seconds_in
    else:
        if self.import_seconds_length >= 60:
            self.import_seconds_length = 0
            self.import_minutes_length = self.import_minutes_length + 1
    update_import_frame_length(self, fps)


def update_import_frames_in(self, context):
    fps = get_fps(context.scene)
    length = self.full_length
    length_timecode = timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_frames_in >= fps and (self.import_seconds_in < max_seconds or self.import_minutes_in < max_minutes):
        #this variable is maxed out, and more can be added to next variables, so cycle up the next variable
        self.import_frames_in = 0
        self.import_seconds_in = self.import_seconds_in + 1
    else:
        if self.import_frames_in + self.import_frames_length >= fps:
            max_seconds = max_seconds - 1
        if self.import_seconds_in + self.import_seconds_length >= max_seconds and self.import_minutes_in + self.import_minutes_length >= max_minutes:
            #all above variables are maxed out in current setup, this cannot be rolled over unless length is lowered
            if self.import_seconds_length > 0 or self.import_minutes_length > 0:
                #reduce seconds length, roll frames up to next
                self.import_seconds_length = self.import_seconds_length - 1
                self.import_frames_length = round(fps) - 1
            elif self.import_frames_length > 1:
                #reduce frame length
                self.import_frames_length = self.import_frames_length - 1
            elif self.import_frames_in + self.import_frames_length >= fps - 1:
                #everything is maxed out, hold at maximum
                self.import_frames_in = max_frames - 1
    update_import_frame_in(self, fps)


def update_import_frames_length(self, context):
    fps = get_fps(context.scene)
    length = self.full_length
    length_timecode = timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length >= max_minutes and self.import_seconds_in + self.import_seconds_length >= max_seconds:
        if self.import_frames_length == 0:
            self.import_frames_length = 1
        elif self.import_frames_length + self.import_frames_in > max_frames:
            self.import_frames_length = max_frames - self.import_frames_in
    else:
        if self.import_frames_length >= fps:
            self.import_frames_length = 0
            self.import_seconds_length = self.import_seconds_length + 1
    update_import_frame_length(self, fps)


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
    draw_tri((in_x, height - half_scale), (in_x + half_scale, height), (in_x + half_scale, height - scale), colorfg)

    if self.in_percent <= .5:
        in_text_x = in_x + scale
    else:
        in_text_x = 0 + half_scale
    draw_text(in_text_x, height - scale + 2, scale - 2, "In: "+str(self.in_frame), colorfg)

    out_x = self.out_percent * width
    draw_rect(out_x - quarter_scale, height - double_scale, quarter_scale, scale, colorfg)
    draw_tri((out_x, height - half_scale - scale), (out_x - half_scale, height - scale), (out_x - half_scale, height - double_scale), colorfg)
    if self.out_percent >= .5:
        out_text_x = 0 + half_scale
    else:
        out_text_x = out_x + half_scale
    draw_text(out_text_x, height - double_scale + 2, scale - 2, "Length: "+str(self.out_frame - self.in_frame), colorfg)


class VSEQF_PT_ThreePointBrowserPanel(bpy.types.Panel):
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
    bl_description = 'Creates a movieclip from the selected video file and sets any visible Movie Clip Editor area to display it'

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


class VSEQF_PT_ThreePointPanel(bpy.types.Panel):
    bl_label = "3 Point Edit"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Track"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
        if not prefs.threepoint:
            return False
        clip = context.space_data.clip
        if clip:
            if os.path.isfile(bpy.path.abspath(clip.filepath)):
                return True
        return False

    def draw(self, context):
        layout = self.layout
        clip = context.space_data.clip

        row = layout.row()
        row.operator('vseqf.threepoint_modal_operator', text='Set In/Out')
        fps = get_fps(context.scene)
        row = layout.row()
        if clip.import_settings.import_frame_in != -1:
            row.label(text="In: "+str(clip.import_settings.import_frame_in)+' ('+timecode_from_frames(clip.import_settings.import_frame_in, fps)+')')
        else:
            row.label(text="In: Not Set")
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
            row.label(text="Length: "+str(clip.import_settings.import_frame_length)+' ('+timecode_from_frames(clip.import_settings.import_frame_length, fps)+')')
        else:
            row.label(text="Length Not Set")
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

    type: bpy.props.StringProperty()

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
                if sound_sequence.frame_final_end > movie_sequence.frame_final_end:
                    sound_sequence.frame_final_end = movie_sequence.frame_final_end
                if context.scene.vseqf.autoparent:
                    sound_sequence.parent = movie_sequence.name
            if context.scene.vseqf.snap_new_end:
                context.scene.frame_current = movie_sequence.frame_final_end

            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class VSEQFThreePointOperator(bpy.types.Operator):
    bl_idname = "vseqf.threepoint_modal_operator"
    bl_label = "3Point Modal Operator"
    bl_description = "Start the realtime 3point editing functionality in the Clip Editor"

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
        fps = round(get_fps(context.scene))
        settings = self.clip.import_settings
        if settings.import_frame_length != -1:
            frame_length = settings.import_frame_length
        else:
            frame_length = self.clip.frame_duration
        if settings.import_frame_in != -1:
            frame_in = settings.import_frame_in
        else:
            frame_in = 0

        remainder, frames_in = divmod(frame_in, fps)
        minutes_in, seconds_in = divmod(remainder, 60)
        remainder, frames_length = divmod(frame_length, fps)
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
            if event.mouse_region_y < 20:
                #click was at bottom of area on timeline, let the user scrub the timeline
                return {'PASS_THROUGH'}
            else:
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
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
        bpy.types.SpaceClipEditor.draw_handler_remove(self._handle, 'WINDOW')
        bpy.ops.scene.delete()
        self.update_import_values(context)
        #context.scene.frame_current = self.start_frame

    def invoke(self, context, event):
        del event
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
        space = context.space_data
        if space.type == 'CLIP_EDITOR':
            self.start_frame = context.scene.frame_current
            self.clip = context.space_data.clip
            self.last_in = self.clip.import_settings.import_frame_in
            self.last_length = self.clip.import_settings.import_frame_length
            self.clip.import_settings.full_length = self.clip.frame_duration
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
    colors = context.preferences.themes[0].user_interface
    text_color = list(colors.wcol_text.text_sel)+[1]
    if self.mode == 'SLIP':
        mode = 'Slip'
    else:
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
        draw_text(window_x, window_y - 6, 12, mode, text_color)


class VSEQFGrabAdd(bpy.types.Operator):
    """Modal operator designed to run in tandem with the built-in grab operator."""
    bl_idname = "vseqf.grabadd"
    bl_label = "Runs in tandem with the grab operator in the vse, adds functionality."

    mode: bpy.props.StringProperty()
    grabbed_sequences = []
    child_sequences = []
    ripple_sequences = []
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
    start_overlay_frame = 0
    snap_edge = None
    snap_edge_sequence = None
    secondary_snap_edge = None
    secondary_snap_edge_sequence = None
    timeline_start = 1
    timeline_end = 1
    timeline_height = 1
    ripple_start = 0
    ripple_left = 0

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

    def reset_sequences(self):
        #used when cancelling, puts everything back to where it was at the beginning by first moving it somewhere safe, then to the true location

        timeline_length = self.timeline_end - self.timeline_start

        for seq in self.sequences:
            sequence = seq[0]
            if not hasattr(sequence, 'input_1'):
                sequence.channel = seq[4] + self.timeline_height
                sequence.frame_start = seq[3] + timeline_length
                sequence.frame_final_start = seq[1] + timeline_length
                sequence.frame_final_end = seq[2] + timeline_length
            else:
                sequence.channel = seq[4] + self.timeline_height
        for seq in self.sequences:
            sequence = seq[0]
            if not hasattr(sequence, 'input_1'):
                sequence.channel = seq[4]
                sequence.frame_start = seq[3]
            else:
                sequence.channel = seq[4]
        return

    def move_sequences(self, offset_x, offset_y):
        #iterates through all sequences and moves them if needed based on what the grab modifier is doing

        ripple_offset = 0

        for seq in self.grabbed_sequences:
            sequence = seq[0]
            #if ripple is enabled, this sequence will affect the position of all sequences after it
            if self.ripple:
                if sequence.select_left_handle and not sequence.select_right_handle and len(self.grabbed_sequences) == 1:
                    #special ripple slide if only one sequence and left handle grabbed
                    sequence.frame_start = seq[3]
                    frame_start = seq[1]
                    ripple_offset = ripple_offset + frame_start - sequence.frame_final_start
                    sequence.frame_start = seq[3] + ripple_offset
                    offset_x = ripple_offset
                else:
                    if self.ripple_pop and sequence.channel != seq[4] and self.sequencer_area_clear(seq[0].frame_final_start, seq[0].frame_final_end, seq[4], sequence.channel):
                        #ripple 'pop'
                        ripple_offset = sequence.frame_final_duration
                        ripple_offset = 0 - ripple_offset
                    else:
                        ripple_offset = seq[2] - sequence.frame_final_end
                        ripple_offset = 0 - ripple_offset
            elif sequence.select_left_handle and not sequence.select_right_handle:
                #fix sequence left handle ripple position when ripple disabled
                if sequence.type not in ['MOVIE', 'SCENE', 'MOVIECLIP'] and sequence.frame_duration == 1:
                    #single images and effects behave differently
                    sequence.frame_final_end = seq[2]
                else:
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
                old_channel = sequence.channel
                old_position = sequence.frame_start
                sequence.channel = new_channel
                #fix sequence position, sometimes can get spazzed out when slipping
                if new_channel != old_channel:
                    sequence.frame_start = old_position

        for seq in self.child_sequences:
            sequence = seq[0]
            new_start = seq[1]
            new_end = seq[2]
            new_pos = seq[3]
            if sequence.parent in self.grabbed_names:
                #this sequence's parent is selected
                parent_data = seq[9]
                parent = parent_data[0]
                new_channel = seq[4] + offset_y
                if new_channel < 1:
                    new_channel = 1
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
                if new_channel < 1:
                    new_channel = 1
                new_start = seq[1] + offset_x
                new_end = seq[2] + offset_x
                new_pos = seq[3] + offset_x
            while sequencer_area_filled(new_start, new_end, new_channel, new_channel, [sequence]):
                new_channel = new_channel + 1
            sequence.channel = new_channel
            sequence.frame_start = new_pos
            sequence.frame_final_start = new_start
            sequence.frame_final_end = new_end

        for seq in self.ripple_sequences:
            #unparented, unselected sequences - need to ripple if enabled
            sequence = seq[0]
            if self.ripple:
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

    def modal(self, context, event):
        if event.type == 'TIMER':
            pass
        if self.mode != 'SLIP':
            #prevent ripple and edge snap while in slip mode
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

            if context.scene.vseqf.snap_cursor_to_edge and not context.screen.is_animation_playing:
                if self.snap_edge:
                    if self.snap_edge == 'left':
                        frame = self.snap_edge_sequence.frame_final_start
                    else:
                        frame = self.snap_edge_sequence.frame_final_end - 1
                    context.scene.frame_current = frame
                    if self.secondary_snap_edge:
                        if self.secondary_snap_edge == 'left':
                            overlay_frame = self.secondary_snap_edge_sequence.frame_final_start
                        else:
                            overlay_frame = self.secondary_snap_edge_sequence.frame_final_end - 1
                        context.scene.sequence_editor.overlay_frame = overlay_frame - frame
        offset_x = 0
        pos_y = self.target_grab_sequence.channel
        if self.target_grab_variable == 'frame_start':
            pos_x = self.target_grab_sequence.frame_start
            offset_x = pos_x - self.target_grab_start
        #elif self.target_grab_variable == 'frame_final_start':
        #    pos_x = self.target_grab_sequence.frame_final_start
        #    offset_x = pos_x - self.target_grab_start
        #elif self.target_grab_variable == 'frame_final_end':
        #    pos_x = self.target_grab_sequence.frame_final_end
        #    offset_x = pos_x - self.target_grab_start

        if self.target_grab_sequence.select_left_handle or self.target_grab_sequence.select_right_handle:
            offset_y = 0
        else:
            offset_y = pos_y - self.target_grab_channel

        self.move_sequences(offset_x, offset_y)

        if event.type in {'LEFTMOUSE', 'RET'}:
            self.remove_draw_handler()
            self.move_sequences(offset_x, offset_y)  #check sequences one last time, just to be sure
            if self.prefs.fades:
                #Fix fades in sequence if they exist
                for seq in self.sequences:
                    sequence = seq[0]
                    if sequence.frame_final_start != seq[1]:
                        #fix fade in
                        fade_curve = get_fade_curve(context, sequence, create=False)
                        if fade_curve:
                            fade_in = fades(fade_curve, sequence, 'detect', 'in', fade_low_point_frame=seq[1])
                            if fade_in > 0:
                                fades(fade_curve, sequence, 'set', 'in', fade_length=fade_in)
                    if sequence.frame_final_end != seq[2]:
                        #fix fade out
                        fade_curve = get_fade_curve(context, sequence, create=False)
                        if fade_curve:
                            fade_out = fades(fade_curve, sequence, 'detect', 'out', fade_low_point_frame=seq[2])
                            if fade_out > 0:
                                fades(fade_curve, sequence, 'set', 'out', fade_length=fade_out)
            if not context.screen.is_animation_playing:
                if self.snap_edge:
                    context.scene.frame_current = self.start_frame
                    context.scene.sequence_editor.overlay_frame = self.start_overlay_frame
                elif self.ripple and self.ripple_pop:
                    context.scene.frame_current = self.ripple_left
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            #cancel movement and put everything back
            if not self.cancelled:
                self.cancelled = True
                current_frame = context.scene.frame_current
                self.ripple = False
                self.ripple_pop = False
                self.reset_sequences()
                #bpy.ops.ed.undo()
                if not context.screen.is_animation_playing:
                    context.scene.frame_current = self.start_frame
                    context.scene.sequence_editor.overlay_frame = self.start_overlay_frame
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
        #   9 parent data
        return [sequence, sequence.frame_final_start, sequence.frame_final_end, sequence.frame_start, sequence.channel, sequence.select, sequence.select_left_handle, sequence.select_right_handle, False, []]

    def invoke(self, context, event):
        self.start_frame = context.scene.frame_current
        self.start_overlay_frame = context.scene.sequence_editor.overlay_frame
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
        self.child_sequences = []
        self.ripple_sequences = []
        self.grabbed_names = []
        sequences = current_sequences(context)
        self.timeline_start = find_sequences_start(sequences)
        self.timeline_end = find_sequences_end(sequences)
        self.ripple_start = self.timeline_end
        self.timeline_height = find_timeline_height(sequences)
        parenting = vseqf_parenting()
        to_move = []
        selected_sequences = current_selected(context)
        for sequence in selected_sequences:
            if sequence.frame_final_start < self.ripple_start and not hasattr(sequence, 'input_1') and not sequence.lock:
                self.ripple_start = sequence.frame_final_end
                self.ripple_left = sequence.frame_final_start
            if parenting:
                to_move = get_recursive(sequence, to_move)
            else:
                to_move.append(sequence)

        #generate grabbed sequences, child sequences and ripple sequences lists
        for sequence in sequences:
            if not sequence.lock and not hasattr(sequence, 'input_1'):
                sequence_data = self.get_sequence_data(sequence)
                self.sequences.append(sequence_data)
                if sequence.select:
                    self.grabbed_names.append(sequence.name)
                    self.grabbed_sequences.append(sequence_data)
                else:
                    if parenting and sequence in to_move:
                        self.child_sequences.append(sequence_data)
                    elif sequence.frame_final_start >= self.ripple_start:
                        self.ripple_sequences.append(sequence_data)
        for seq in self.child_sequences:
            sequence = seq[0]
            parent_data = self.find_by_name(sequence.parent)
            seq[9] = parent_data
        self._timer = context.window_manager.event_timer_add(time_step=0.01, window=context.window)
        self.ripple_sequences.sort(key=lambda x: x[1])
        self.grabbed_sequences.sort(key=lambda x: x[1])
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

        #Determine the snap edges
        self.snap_edge = None
        self.snap_edge_sequence = None
        self.secondary_snap_edge = None
        self.secondary_snap_edge_sequence = None
        #Determine number of selected edges in grabbed sequences:
        selected_edges = []
        for sequence_data in self.grabbed_sequences:
            if sequence_data[6]:
                selected_edges.append([sequence_data[0], 'left'])
            if sequence_data[7]:
                selected_edges.append([sequence_data[0], 'right'])
        if len(selected_edges) == 1:
            #only one edge is grabbed, snap to it
            self.snap_edge_sequence = selected_edges[0][0]
            self.snap_edge = selected_edges[0][1]
        elif len(selected_edges) == 2:
            #two sequence edges are selected
            #if one sequence is active, make that primary
            active = current_active(context)
            if selected_edges[0][0] == active and selected_edges[1][0] != active:
                self.snap_edge = selected_edges[0][1]
                self.snap_edge_sequence = selected_edges[0][0]
                self.secondary_snap_edge = selected_edges[1][1]
                self.secondary_snap_edge_sequence = selected_edges[1][0]
            elif selected_edges[1][0] == active and selected_edges[0][0] != active:
                self.snap_edge = selected_edges[1][1]
                self.snap_edge_sequence = selected_edges[1][0]
                self.secondary_snap_edge = selected_edges[0][1]
                self.secondary_snap_edge_sequence = selected_edges[0][0]
            else:
                #neither sequence is active, or both are the same sequence, make rightmost primary, leftmost secondary
                if selected_edges[0][1] == 'left':
                    first_frame = selected_edges[0][0].frame_final_start
                else:
                    first_frame = selected_edges[0][0].frame_final_end
                if selected_edges[1][1] == 'left':
                    second_frame = selected_edges[1][0].frame_final_start
                else:
                    second_frame = selected_edges[1][0].frame_final_end
                if first_frame > second_frame:
                    self.snap_edge = selected_edges[0][1]
                    self.snap_edge_sequence = selected_edges[0][0]
                    self.secondary_snap_edge = selected_edges[1][1]
                    self.secondary_snap_edge_sequence = selected_edges[1][0]
                else:
                    self.snap_edge = selected_edges[1][1]
                    self.snap_edge_sequence = selected_edges[1][0]
                    self.secondary_snap_edge = selected_edges[0][1]
                    self.secondary_snap_edge_sequence = selected_edges[0][0]

        if not self.target_grab_sequence:
            #nothing selected... is this possible?
            return {'CANCELLED'}
        if len(self.grabbed_sequences) == 1 and not (self.grabbed_sequences[0][0].select_left_handle or self.grabbed_sequences[0][0].select_right_handle):
            self.can_pop = True
        else:
            self.can_pop = False
        #bpy.ops.ed.undo_push()
        context.window_manager.modal_handler_add(self)
        args = (self, context)
        self._handle = bpy.types.SpaceSequenceEditor.draw_handler_add(vseqf_grab_draw, args, 'WINDOW', 'POST_PIXEL')
        return {'RUNNING_MODAL'}


class VSEQFGrab(bpy.types.Operator):
    """Wrapper operator for the built-in grab operator, runs the added features as well as the original."""
    bl_idname = "vseqf.grab"
    bl_label = "Replacement for the default grab operator with more features"

    mode: bpy.props.StringProperty("")

    def execute(self, context):
        del context
        bpy.ops.vseqf.grabadd('INVOKE_DEFAULT', mode=self.mode)
        if self.mode == "TIME_EXTEND":
            bpy.ops.transform.transform("INVOKE_DEFAULT", mode=self.mode)
        elif self.mode == "SLIP":
            bpy.ops.sequencer.slip('INVOKE_DEFAULT')
        else:
            bpy.ops.transform.seq_slide('INVOKE_DEFAULT')
        self.mode = ''
        return {'FINISHED'}


class VSEQFContextMenu(bpy.types.Operator):
    bl_idname = "vseqf.context_menu"
    bl_label = "Open Context Menu"

    click_mode = None
    marker_area_height = 40

    def invoke(self, context, event):
        self.click_mode = context.window_manager.keyconfigs.active.preferences.select_mouse
        if event.type == 'RIGHTMOUSE':
            if self.click_mode == 'RIGHT':
                return {'CANCELLED'}
        self.context_menu(context, event)
        return {'FINISHED'}

    def context_menu(self, context, event):
        region = context.region
        view = region.view2d
        distance_multiplier = 15
        location = view.region_to_view(event.mouse_region_x, event.mouse_region_y)
        click_frame, click_channel = location
        active = current_active(context)

        #determine distance scale
        width = region.width
        left, bottom = view.region_to_view(0, 0)
        right, bottom = view.region_to_view(width, 0)
        shown_width = right - left
        frame_px = width / shown_width
        distance = distance_multiplier / frame_px

        if abs(click_frame - context.scene.frame_current) <= distance:
            #clicked on cursor
            bpy.ops.wm.call_menu(name='VSEQF_MT_context_cursor')
        elif event.mouse_region_y <= self.marker_area_height:
            is_near_marker = near_marker(context, click_frame)
            if is_near_marker:
                #clicked on marker
                context.scene.vseqf.current_marker_frame = is_near_marker.frame
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_marker')
        elif active and on_sequence(click_frame, click_channel, active):
            #clicked on sequence
            active_size = active.frame_final_duration * frame_px
            if abs(click_frame - active.frame_final_start) <= distance * 2 and active_size > 60:
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_sequence_left')
            elif abs(click_frame - active.frame_final_end) <= distance * 2 and active_size > 60:
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_sequence_right')
            else:
                bpy.ops.wm.call_menu(name="VSEQF_MT_context_sequence")
        else:
            #clicked on empty area
            bpy.ops.wm.call_menu(name='VSEQF_MT_context_none')


class VSEQFSelectGrab(bpy.types.Operator):
    """Replacement for the right and left-click select operator and context menu"""
    bl_idname = "vseqf.select_grab"
    bl_label = "Grab/Move Sequence"

    mouse_start_x = 0
    mouse_start_y = 0
    mouse_start_region_x = 0
    mouse_start_region_y = 0
    selected = []
    marker_area_height = 40
    _timer = None
    click_mode = None

    def modal(self, context, event):
        region = context.region
        view = region.view2d
        move_target = 10
        if event.type == 'MOUSEMOVE':
            delta_x = abs(self.mouse_start_x - event.mouse_x)
            delta_y = abs(self.mouse_start_y - event.mouse_y)
            if delta_x > move_target or delta_y > move_target:
                if context.scene.vseqf.grab_multiselect:
                    self.restore_selected()
                location = view.region_to_view(self.mouse_start_region_x, self.mouse_start_region_y)
                click_frame, click_channel = location
                is_near_marker = near_marker(context, click_frame)
                if event.mouse_region_y <= self.marker_area_height:
                    if is_near_marker:
                        bpy.ops.vseqf.quickmarkers_move(frame=is_near_marker.frame)
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
        self.click_mode = context.window_manager.keyconfigs.active.preferences.select_mouse
        if event.type == 'RIGHTMOUSE':
            #right click, maybe do context menus
            bpy.ops.vseqf.context_menu('INVOKE_DEFAULT')
            if self.click_mode == 'LEFT':
                return {'FINISHED'}
        bpy.ops.ed.undo_push()
        self.selected = []
        selected_sequences = current_selected(context)
        for sequence in selected_sequences:
            self.selected.append([sequence, sequence.select_left_handle, sequence.select_right_handle])
        if event.mouse_region_y > self.marker_area_height:
            bpy.ops.sequencer.select('INVOKE_DEFAULT', deselect_all=True)
        selected_sequences = current_selected(context)
        if not selected_sequences:
            return {'FINISHED'}
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
        self.mouse_start_region_x = event.mouse_region_x
        self.mouse_start_region_y = event.mouse_region_y
        self._timer = context.window_manager.event_timer_add(time_step=0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


class VSEQFDoubleUndo(bpy.types.Operator):
    """Undo previous action"""
    bl_idname = "vseqf.double_undo"
    bl_label = "Undo previous action"

    def execute(self, context):
        del context
        bpy.ops.ed.undo()
        bpy.ops.ed.undo()
        return {'FINISHED'}


class VSEQFContextMarker(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_context_marker'
    bl_label = 'Marker Operations'

    def draw(self, context):
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        layout.separator()
        if inside_meta_strip():
            layout.operator('vseqf.meta_exit')
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
    bl_idname = "VSEQF_MT_context_cursor"
    bl_label = "Cursor Operations"

    def draw(self, context):
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        layout.separator()
        if inside_meta_strip():
            layout.operator('vseqf.meta_exit')
            layout.separator()
        props = layout.operator("sequencer.strip_jump", text="Jump to Previous Strip")
        props.next = False
        props.center = False
        props = layout.operator("sequencer.strip_jump", text="Jump to Next Strip")
        props.next = True
        props.center = False
        layout.separator()
        layout.label(text='Snap:')
        layout.operator('vseqf.quicksnaps', text='Cursor To Nearest Second').type = 'cursor_to_seconds'
        sequence = current_active(context)
        if sequence:
            layout.operator('vseqf.quicksnaps', text='Cursor To Beginning Of Sequence').type = 'cursor_to_beginning'
            layout.operator('vseqf.quicksnaps', text='Cursor To End Of Sequence').type = 'cursor_to_end'
            layout.operator('vseqf.quicksnaps', text='Selected To Cursor').type = 'selection_to_cursor'
            layout.operator('vseqf.quicksnaps', text='Sequence Beginning To Cursor').type = 'begin_to_cursor'
            layout.operator('vseqf.quicksnaps', text='Sequence End To Cursor').type = 'end_to_cursor'


class VSEQFContextNone(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_context_none'
    bl_label = "Operations On Sequence Editor"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        layout.separator()
        if inside_meta_strip():
            layout.operator('vseqf.meta_exit')
            layout.separator()
        layout.menu('SEQUENCER_MT_add')
        layout.menu('VSEQF_MT_quickzooms_menu')


class VSEQFContextSequenceLeft(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_sequence_left"
    bl_label = "Operations On Left Handle"

    def draw(self, context):
        strip = current_active(context)
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        if inside_meta_strip():
            layout.separator()
            layout.operator('vseqf.meta_exit')
        if strip:
            layout.separator()
            layout.prop(context.scene.vseqf, 'fade')
            layout.operator('vseqf.quickfades_set', text='Set Fade In').type = 'in'
            props = layout.operator('vseqf.quickfades_clear', text='Clear Fade In')
            props.direction = 'in'
            props.active_only = True


class VSEQFContextSequenceRight(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_sequence_right"
    bl_label = "Operations On Right Handle"

    def draw(self, context):
        strip = current_active(context)
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        if inside_meta_strip():
            layout.separator()
            layout.operator('vseqf.meta_exit')
        if strip:
            layout.separator()
            layout.prop(context.scene.vseqf, 'fade')
            layout.operator('vseqf.quickfades_set', text='Set Fade Out').type = 'out'
            props = layout.operator('vseqf.quickfades_clear', text='Clear Fade Out')
            props.direction = 'out'
            props.active_only = True


class VSEQFContextSequence(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_sequence"
    bl_label = "Operations On Sequence"

    def draw(self, context):
        prefs = get_prefs()
        strip = current_active(context)
        selected = current_selected(context)
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        if inside_meta_strip():
            layout.separator()
            layout.operator('vseqf.meta_exit')
        if strip:
            layout.separator()
            layout.label(text='Active Sequence:')
            layout.prop(strip, 'mute')
            layout.prop(strip, 'lock')
            if prefs.tags:
                layout.menu('VSEQF_MT_quicktags_menu')
            if strip.type == 'META':
                layout.operator('sequencer.meta_toggle', text='Enter Meta Strip')
                layout.operator('sequencer.meta_separate')
        if selected:
            layout.separator()
            layout.label(text='Selected Sequence(s):')
            layout.operator('sequencer.meta_make')
            if prefs.cuts:
                layout.menu('VSEQF_MT_quickcuts_menu')
            if prefs.parenting:
                layout.menu('VSEQF_MT_quickparents_menu')
            layout.operator('sequencer.duplicate_move', text='Duplicate')
            layout.operator('vseqf.grab', text='Grab/Move')


#Functions related to QuickSpeed
@persistent
def frame_step(scene):
    """Handler that skips frames when the speed step value is used
    Argument:
        scene: the current Scene"""

    if bpy.context.scene != scene:
        return
    if scene.vseqf.step in [-1, 0, 1]:
        return
    difference = scene.frame_current - scene.vseqf.last_frame
    if difference == -1 or difference == 1:
        frame_skip = difference * (abs(scene.vseqf.step) - 1)
        bpy.ops.screen.frame_offset(delta=frame_skip)
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
    if context.space_data.view_type != 'PREVIEW':
        layout.prop(scene.vseqf, 'follow', text='Follow Cursor', toggle=True)


def start_follow(_, context):
    if context.scene.vseqf.follow:
        bpy.ops.vseqf.follow('INVOKE_DEFAULT')


def draw_quickzoom_menu(self, context):
    """Draws the submenu for the QuickZoom shortcuts, placed in the sequencer view menu"""
    del context
    layout = self.layout
    layout.menu('VSEQF_MT_quickzooms_menu', text="Quick Zoom")


def zoom_custom(begin, end, bottom=None, top=None, preroll=True):
    """Zooms to an area on the sequencer timeline by adding a temporary strip, zooming to it, then deleting that strip.
    Note that this function will retain selected and active sequences.
    Arguments:
        begin: The starting frame of the zoom area
        end: The ending frame of the zoom area
        bottom: The lowest visible channel
        top: The topmost visible channel
        preroll: If true, add a buffer before the beginning"""

    del bottom  #Add in someday...
    del top     #Add in someday...
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
    bl_idname = "VSEQF_MT_quickzooms_menu"
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
            layout.menu('VSEQF_MT_quickzoom_preset_menu')

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
    bl_idname = "VSEQF_MT_quickzoom_preset_menu"
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

    name: bpy.props.StringProperty()

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

    name: bpy.props.StringProperty()

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

    mode: bpy.props.StringProperty()

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
    area: bpy.props.StringProperty()

    def execute(self, context):
        #return bpy.ops.view2d.smoothview("INVOKE_DEFAULT", xmin=0, xmax=10, ymin=0, ymax=10, wait_for_input=False)
        if self.area.isdigit():
            #Zoom value is a number of seconds
            scene = context.scene
            cursor = scene.frame_current
            zoom_custom(cursor, (cursor + (get_fps(scene) * int(self.area))))
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
    cursor_target = 0
    animation_playing_last = False
    skip_first_click = True

    _timer = None

    def modal(self, context, event):
        view = self.view
        if not context.scene.vseqf.follow:
            return {'CANCELLED'}
        if context.screen.is_animation_playing and not self.animation_playing_last:
            self.recalculate_target(context)
        if event.type == 'LEFTMOUSE' and context.screen.is_animation_playing:
            if self.skip_first_click:
                self.skip_first_click = False
            else:
                old_x = self.view.view_to_region(context.scene.frame_current, 0, clip=False)[0]
                new_x = event.mouse_region_x
                delta_x = new_x - old_x
                self.cursor_target = self.cursor_target + delta_x

        if event.type == 'TIMER':
            if context.screen.is_animation_playing:
                override = context.copy()
                override['region'] = self.region
                override['view2d'] = self.view
                cursor_location = view.view_to_region(context.scene.frame_current, 0, clip=False)[0]
                if cursor_location != 12000:
                    offset = (self.cursor_target - cursor_location)
                    bpy.ops.view2d.pan(override, deltax=-offset)
        self.animation_playing_last = context.screen.is_animation_playing
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        del event
        self.animation_playing_last = context.screen.is_animation_playing
        if context.screen.is_animation_playing:
            #Need to put this in to prevent blender from changing cursor position when the click that STARTED this is caught
            self.skip_first_click = True
        else:
            self.skip_first_click = False
        area = context.area
        for region in area.regions:
            if region.type == 'WINDOW':
                self.region = region
                self.view = region.view2d
        if self.region is None or self.view is None:
            return {'CANCELLED'}
        if context.screen.is_animation_playing:
            self.recalculate_target(context)
        self._timer = context.window_manager.event_timer_add(time_step=0.25, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def recalculate_target(self, context):
        cursor_location = self.view.view_to_region(context.scene.frame_current, 0, clip=True)[0]
        if cursor_location == 12000:
            self.cursor_target = round(self.region.width / 4)
        else:
            self.cursor_target = cursor_location


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


def get_fade_curve(context, sequence, create=False):
    #Returns the fade curve for a given sequence.  If create is True, a curve will always be returned, if False, None will be returned if no curve is found.
    if sequence.type == 'SOUND':
        fade_variable = 'volume'
    else:
        fade_variable = 'blend_alpha'

    #Search through all curves and find the fade curve
    animation_data = context.scene.animation_data
    if not animation_data:
        if create:
            context.scene.animation_data_create()
            animation_data = context.scene.animation_data
        else:
            return None
    action = animation_data.action
    if not action:
        if create:
            action = bpy.data.actions.new(sequence.name+'Action')
            animation_data.action = action
        else:
            return None

    all_curves = action.fcurves
    fade_curve = None  #curve for the fades
    for curve in all_curves:
        if curve.data_path == 'sequence_editor.sequences_all["'+sequence.name+'"].'+fade_variable:
            #keyframes found
            fade_curve = curve
            break

    #Create curve if needed
    if fade_curve is None and create:
        fade_curve = all_curves.new(data_path=sequence.path_from_id(fade_variable))

        #add a single keyframe to prevent blender from making the waveform invisible (bug)
        volume = sequence.volume
        fade_curve.keyframe_points.add(1)
        point = fade_curve.keyframe_points[0]
        point.co = (sequence.frame_final_start, volume)

    return fade_curve


def fades(fade_curve, sequence, mode, direction, fade_length=0, fade_low_point_frame=False):
    """Detects, creates, and edits fadein and fadeout for sequences.
    Arguments:
        fade_curve: Curve to detect or adjust fades on
        sequence: VSE Sequence object that will be operated on
        mode: String, determines the operation that will be done
            detect: determines the fade length set to the sequence
            set: sets a desired fade length to the sequence
        direction: String, determines if the function works with fadein or fadeout
            in: fadein is operated on
            out: fadeout is operated on
        fade_length: Integer, optional value used only when setting fade lengths
        fade_low_point_frame: Integer, optional value used for detecting a fade at a point other than at the edge of the sequence"""

    if sequence.type == 'SOUND':
        fade_variable = 'volume'
    else:
        fade_variable = 'blend_alpha'

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

    #Detect fades or add if set mode
    fade_keyframes = fade_curve.keyframe_points
    if len(fade_keyframes) == 0:
        #no keyframes found, create them if instructed to do so
        if mode == 'set':
            fade_max_value = getattr(sequence, fade_variable)
            set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value)
        else:
            return 0

    elif len(fade_keyframes) == 1:
        #only one keyframe, use y value of keyframe as the max value for a new fade
        if mode == 'set':
            #determine fade_max_value from value at one keyframe
            fade_max_value = fade_keyframes[0].co[1]
            if fade_max_value == 0:
                fade_max_value = 1

            #add new fade
            set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value)
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
                        set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point, fade_high_point=fade_high_point)
                        return fade_length
                    else:
                        #fade detected!
                        return abs(fade_high_point.co[0] - fade_low_point.co[0])
                else:
                    #fade high point is not valid, low point is tho
                    if mode == 'set':
                        fade_max_value = fade_curve.evaluate(fade_high_point_frame)
                        set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point)
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
                        set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point, fade_high_point=fade_high_point)
                        return fade_length
                    else:
                        #no valid fade high point
                        fade_max_value = fade_curve.evaluate(fade_high_point_frame)
                        set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=fade_low_point)
                        return fade_length
                else:
                    return 0

        else:
            #no valid fade detected, other keyframes are on the curve tho
            if mode == 'set':
                fade_max_value = fade_curve.evaluate(fade_high_point_frame)
                set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value)
                return fade_length
            else:
                return 0


def set_fade(fade_curve, direction, fade_low_point_frame, fade_high_point_frame, fade_max_value, fade_low_point=None, fade_high_point=None):
    """Create or change a fadein or fadeout on  a set of keyframes
    Arguments:
        fade_curve: the curve that the keyframes belong to
        direction: String, determines if a fadein or fadeout will be set
            'in': Set a fadein
            'out': Set a fadeout
        fade_low_point_frame: Integer, the frame at which the fade should be at its lowest value
        fade_high_point_frame: Integer, the frame at which the fade should be at its highest value
        fade_max_value: Float, the y value for the high point of the fade
        fade_low_point: Optional, a keyframe point for the low point of the fade curve that should be moved, instead of creating a new one
        fade_high_point: Optional, a keyframe point for the high point of the fade curve that should be moved, instead of creating a new one"""

    fade_keyframes = fade_curve.keyframe_points

    #check if any keyframe points other than the fade high and low points are in the fade area, delete them if needed
    for keyframe in fade_keyframes:
        if direction == 'in':
            if (keyframe.co[0] < fade_high_point_frame) and (keyframe.co[0] > fade_low_point_frame):
                if (keyframe != fade_low_point) and (keyframe != fade_high_point):
                    try:
                        fade_keyframes.remove(keyframe)
                    except:
                        pass
        if direction == 'out':
            if (keyframe.co[0] > fade_high_point_frame) and (keyframe.co[0] < fade_low_point_frame):
                if (keyframe != fade_low_point) and (keyframe != fade_high_point):
                    try:
                        fade_keyframes.remove(keyframe)
                    except:
                        pass
    fade_length = abs(fade_high_point_frame - fade_low_point_frame)
    handle_offset = fade_length * .38
    if fade_length == 0:
        #remove fade
        if direction == 'in' and fade_high_point:
            fade_keyframes.remove(fade_high_point)
        fade_keyframes.remove(fade_low_point)
        if direction == 'out' and fade_high_point:
            fade_keyframes.remove(fade_high_point)
        if len(fade_keyframes) == 0:
            #curve is empty, remove it
            try:
                bpy.context.scene.animation_data.action.fcurves.remove(fade_curve)
            except:
                pass
        return

    if fade_high_point:
        #move fade high point to where it should be
        fade_high_point.co = (fade_high_point_frame, fade_max_value)
        fade_high_point.handle_left = (fade_high_point_frame - handle_offset, fade_max_value)
        fade_high_point.handle_right = (fade_high_point_frame + handle_offset, fade_max_value)
    else:
        #create new fade high point
        fade_keyframes.insert(frame=fade_high_point_frame, value=fade_max_value)
    if fade_low_point:
        #move fade low point to where it should be
        fade_low_point.co = (fade_low_point_frame, 0)
        fade_low_point.handle_left = (fade_low_point_frame - handle_offset, 0)
        fade_low_point.handle_right = (fade_low_point_frame + handle_offset, 0)
    else:
        #create new fade low point
        fade_keyframes.insert(frame=fade_low_point_frame, value=0)


def fade_operator_draw(self, context):
    #Draw current fade info overlays
    region = context.region
    view = region.view2d
    for data in self.strip_data:
        sequence = data['sequence']
        fade_in = data['fade_in']
        fade_out = data['fade_out']
        channel_buffer = 0.05
        channel_bottom = sequence.channel + channel_buffer
        channel_top = sequence.channel + 1 - channel_buffer
        if fade_in > 0:
            strip_left, strip_bottom = view.view_to_region(sequence.frame_final_start, channel_bottom, clip=False)
            fade_in_loc, strip_top = view.view_to_region(sequence.frame_final_start + fade_in, channel_top, clip=False)
            draw_line(strip_left, strip_bottom, fade_in_loc, strip_top, color=(.8, .2, .2, 1))
            draw_text(fade_in_loc, strip_top - 12, 11, str(int(fade_in)), color=(1, 1, 1, 1))
        if fade_out > 0:
            strip_right, strip_bottom = view.view_to_region(sequence.frame_final_end, channel_bottom, clip=False)
            fade_out_loc, strip_top = view.view_to_region(sequence.frame_final_end - fade_out, channel_top, clip=False)
            draw_line(strip_right, strip_bottom, fade_out_loc, strip_top, color=(.8, .2, .2, 1))
            draw_text(fade_out_loc, strip_top - 12, 11, str(int(fade_out)), justify='right', color=(1, 1, 1, 1))


class VSEQFModalFades(bpy.types.Operator):
    bl_idname = 'vseqf.modal_fades'
    bl_label = "Add and modify strip fade in and out"
    bl_options = {'REGISTER', 'BLOCKING', 'GRAB_CURSOR'}

    mode: bpy.props.EnumProperty(name='Fade To Set', default="DEFAULT", items=[("DEFAULT", "Based On Selection", "", 1), ("LEFT", "Fade In", "", 2), ("RIGHT", "Fade Out", "", 3), ("BOTH", "Fade In And Out", "", 4)])
    strip_data = []
    snap_to_frame = 0
    snap_edges = []
    mouse_last_x = 0
    mouse_last_y = 0
    mouse_move_x = 0
    mouse_move_y = 0
    mouse_start_region_x = 0
    mouse_start_region_y = 0

    value = ''  #Used for storing typed-in grab values

    mouse_scale_x = 1  #Frames to move sequences per pixel of mouse x movement
    mouse_scale_y = 1  #Channels to move sequences per pixel of mouse y movement

    view_frame_start = 0  #Leftmost frame in the 2d view
    view_frame_end = 0  #Rightmost frame in the 2d view
    view_channel_start = 0  #Lowest channel in the 2d view
    view_channel_end = 0  #Highest channel in the 2d view

    def remove_draw_handler(self):
        bpy.types.SpaceSequenceEditor.draw_handler_remove(self._handle, 'WINDOW')

    def get_fades(self, sequence, fade_mode, fade_curve):
        fade_in = 0
        fade_out = 0
        if fade_mode in ['LEFT', 'BOTH']:
            fade_in = fades(fade_curve, sequence, 'detect', 'in')
        if fade_mode in ['RIGHT', 'BOTH']:
            fade_out = fades(fade_curve, sequence, 'detect', 'out')
        return [fade_in, fade_out]

    def modal(self, context, event):
        reset_fades = False
        area = context.area
        if event.value == 'PRESS':
            if event.type in ["F", "MIDDLEMOUSE"]:
                reset_fades = True
                #Switch between fade modes
                if self.mode == 'DEFAULT':
                    self.mode = 'LEFT'
                elif self.mode == 'LEFT':
                    self.mode = 'RIGHT'
                elif self.mode == 'RIGHT':
                    self.mode = 'BOTH'
                elif self.mode == 'BOTH':
                    self.mode = 'DEFAULT'
            elif event.type in ['L', 'S']:
                reset_fades = True
                self.mode = 'LEFT'
            elif event.type in ['R', 'E']:
                reset_fades = True
                self.mode = 'RIGHT'
            elif event.type == 'B':
                reset_fades = True
                self.mode = 'BOTH'
            elif event.type == 'C':
                reset_fades = True
                self.mode = 'DEFAULT'
            else:
                self.value = add_to_value(self.value, event.type, is_float=False)

        #Calculate movement variables
        mouse_delta_x = event.mouse_x - self.mouse_last_x
        mouse_move_delta_x = mouse_delta_x * self.mouse_scale_x
        mouse_delta_y = event.mouse_y - self.mouse_last_y
        mouse_move_delta_y = mouse_delta_y * self.mouse_scale_x
        self.mouse_last_x = event.mouse_x
        self.mouse_last_y = event.mouse_y
        if event.shift:  #Slow movement
            mouse_move_delta_x = mouse_move_delta_x * .1
            mouse_move_delta_y = mouse_move_delta_y * .1
        self.mouse_move_x = self.mouse_move_x + mouse_move_delta_x
        self.mouse_move_y = self.mouse_move_y + mouse_move_delta_y

        mouse_frame, mouse_channel = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        offset_x = int(round(self.mouse_move_x))
        offset_y = int(round(self.mouse_move_y))

        #Override movement if snapping is enabled
        snapping = False
        if event.ctrl and self.snap_edges:
            self.snap_to_frame = min(self.snap_edges, key=lambda x: abs(x - mouse_frame))
            snapping = True

        #Display information
        header_text = ''
        if self.mode == 'DEFAULT':
            header_text = "Adjusting fades based on strip selections."
        elif self.mode == 'LEFT':
            header_text = "Adjusting fade-in on selected strips."
        elif self.mode == 'RIGHT':
            header_text = "Adjusting fade-out on selected strips."
        elif self.mode == 'BOTH':
            header_text = "Adjusting fade-in and fade-out on selected strips."
        if self.value:
            header_text = 'Fade length: ' + self.value + '.  ' + header_text
        area.header_text_set(header_text)
        status_text = "Move mouse up/down to bring fades towards/away from middle of each strip, move mouse left/right to move all fades left/right.  Press F or MiddleMouse to switch modes.  Type in a value to set all fades to that value."
        context.workspace.status_text_set(status_text)

        #Adjust fades
        for data in self.strip_data:
            sequence = data['sequence']

            if reset_fades:
                data['fade_in'] = data['original_fade_in']
                data['fade_out'] = data['original_fade_out']

            if self.mode == 'DEFAULT':
                fade_mode = data['fade_mode']
            else:
                fade_mode = self.mode
            if fade_mode in ['LEFT', 'BOTH']:
                #Handle fade-in
                fade_in = data['original_fade_in']
                if self.value:
                    new_fade_in = int(self.value)
                elif snapping:
                    new_fade_in = self.snap_to_frame - sequence.frame_final_start
                else:
                    new_fade_in = fade_in + offset_x + offset_y
                if new_fade_in < 0:
                    new_fade_in = 0
                if new_fade_in > sequence.frame_final_duration:
                    new_fade_in = sequence.frame_final_duration
                data['fade_in'] = new_fade_in

            if fade_mode in ['RIGHT', 'BOTH']:
                #handle fade-out
                fade_out = data['original_fade_out']
                if self.value:
                    new_fade_out = int(self.value)
                elif snapping:
                    new_fade_out = sequence.frame_final_end - self.snap_to_frame
                else:
                    new_fade_out = fade_out - offset_x + offset_y
                if new_fade_out < 0:
                    new_fade_out = 0
                if new_fade_out > sequence.frame_final_duration:
                    new_fade_out = sequence.frame_final_duration
                data['fade_out'] = new_fade_out

            if fade_mode == 'BOTH':
                #Check if fades are too long for each other
                fade_in = data['fade_in']
                fade_out = data['fade_out']
                if fade_in + fade_out >= sequence.frame_final_duration:
                    fade_overdrive = fade_in + fade_out
                    fade_over_percent = fade_overdrive / sequence.frame_final_duration
                    data['fade_in'] = int(fade_in / fade_over_percent)
                    data['fade_out'] = int(fade_out / fade_over_percent)

        area.tag_redraw()

        if event.type in {'LEFTMOUSE', 'RET'}:
            #finalize fades
            for data in self.strip_data:
                sequence = data['sequence']
                fade_curve = data['fade_curve']
                fade_in = data['fade_in']
                fade_out = data['fade_out']
                if fade_in != data['original_fade_in']:
                    fades(fade_curve, sequence, 'set', 'in', fade_length=fade_in)
                if fade_out != data['original_fade_out']:
                    fades(fade_curve, sequence, 'set', 'out', fade_length=fade_out)
            self.remove_draw_handler()
            area.header_text_set(None)
            context.workspace.status_text_set(None)
            self.mode = 'DEFAULT'
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            #cancel fades and put everything back
            self.remove_draw_handler()
            area.header_text_set(None)
            context.workspace.status_text_set(None)
            bpy.ops.ed.undo()
            self.mode = 'DEFAULT'
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        selected = context.selected_sequences
        if not selected:
            self.mode = 'DEFAULT'
            return {'CANCELLED'}

        bpy.ops.ed.undo_push()
        bpy.ops.ed.undo_push()

        self.mouse_move_x = 0
        self.mouse_move_y = 0
        self.value = ''

        #Store strip data for quick access, and to prevent it from being overwritten
        self.strip_data = []
        self.snap_edges = [context.scene.frame_current]
        for sequence in context.sequences:
            self.snap_edges.extend([sequence.frame_final_start, sequence.frame_final_end])
            if sequence.select:
                fade_curve = get_fade_curve(context, sequence, create=True)

                if sequence.select_left_handle and not sequence.select_right_handle:
                    fade_mode = 'LEFT'
                elif sequence.select_right_handle and not sequence.select_left_handle:
                    fade_mode = 'RIGHT'
                else:
                    fade_mode = 'BOTH'
                fade_in, fade_out = self.get_fades(sequence, fade_mode, fade_curve)
                data = {
                    'sequence': sequence,
                    'fade_mode': fade_mode,
                    'fade_in': fade_in,
                    'fade_out': fade_out,
                    'original_fade_in': fade_in,
                    'original_fade_out': fade_out,
                    'fade_curve': fade_curve
                }
                self.strip_data.append(data)

        self.snap_edges = list(set(self.snap_edges))  #Sort and remove doubles

        #Stores the current position of the mouse
        self.mouse_last_x = event.mouse_x
        self.mouse_last_y = event.mouse_y
        self.mouse_start_region_x = event.mouse_region_x
        self.mouse_start_region_y = event.mouse_region_y

        #Determines how far a fade should move per pixel that the mouse moves
        region = context.region
        view = region.view2d
        self.view_frame_start, self.view_channel_start = view.region_to_view(0, 0)
        self.view_frame_end, self.view_channel_end = view.region_to_view(region.width, region.height)
        region = context.region
        frames_width = self.view_frame_end - self.view_frame_start
        channels_height = self.view_channel_end - self.view_channel_start
        self.mouse_scale_x = frames_width / region.width
        self.mouse_scale_y = channels_height / region.height

        context.window_manager.modal_handler_add(self)
        args = (self, context)
        self._handle = bpy.types.SpaceSequenceEditor.draw_handler_add(fade_operator_draw, args, 'WINDOW', 'POST_PIXEL')
        return {'RUNNING_MODAL'}


class VSEQF_PT_QuickFadesPanel(bpy.types.Panel):
    """Panel for QuickFades operators and properties.  Placed in the VSE properties area."""
    bl_label = "Fade In/Out"
    bl_parent_id = "SEQUENCER_PT_adjust"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
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
        fade_curve = get_fade_curve(context, active_sequence, create=False)
        if fade_curve:
            fadein = fades(fade_curve, active_sequence, 'detect', 'in')
            fadeout = fades(fade_curve, active_sequence, 'detect', 'out')
        else:
            fadein = 0
            fadeout = 0

        layout = self.layout

        #First row, detected fades
        row = layout.row()
        if fadein > 0:
            row.label(text="Fadein: "+str(round(fadein))+" Frames")
        else:
            row.label(text="No Fadein Detected")
        if fadeout > 0:
            row.label(text="Fadeout: "+str(round(fadeout))+" Frames")
        else:
            row.label(text="No Fadeout Detected")

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
    bl_idname = "VSEQF_MT_quickfades_menu"
    bl_label = "Quick Fades"

    @classmethod
    def poll(cls, context):
        del context
        prefs = get_prefs()
        return prefs.fades

    def draw(self, context):
        scene = context.scene
        sequences = current_selected(context)
        sequence = current_active(context)

        layout = self.layout
        if sequence and len(sequences) > 0:
            #If a sequence is active
            vseqf = scene.vseqf
            fade_curve = get_fade_curve(context, sequence, create=False)
            if fade_curve:
                fadein = fades(fade_curve, sequence, 'detect', 'in')
                fadeout = fades(fade_curve, sequence, 'detect', 'out')
            else:
                fadein = 0
                fadeout = 0

            #Detected fades section
            if fadein > 0:
                layout.label(text="Fadein: "+str(round(fadein))+" Frames")
            else:
                layout.label(text="No Fadein Detected")
            if fadeout > 0:
                layout.label(text="Fadeout: "+str(round(fadeout))+" Frames")
            else:
                layout.label(text="No Fadeout Detected")

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
            layout.label(text="No Sequence Selected")


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
    type: bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        #iterate through selected sequences and apply fades to them
        selected_sequences = current_selected(context)
        for sequence in selected_sequences:
            fade_curve = get_fade_curve(context, sequence, create=True)
            if self.type == 'both':
                fades(fade_curve, sequence, 'set', 'in', fade_length=context.scene.vseqf.fade)
                fades(fade_curve, sequence, 'set', 'out', fade_length=context.scene.vseqf.fade)
            else:
                fades(fade_curve, sequence, 'set', self.type, fade_length=context.scene.vseqf.fade)

        redraw_sequencers()
        return{'FINISHED'}


class VSEQFQuickFadesClear(bpy.types.Operator):
    """Operator to clear fades on selected sequences"""
    bl_idname = 'vseqf.quickfades_clear'
    bl_label = 'VSEQF Quick Fades Clear Fades'
    bl_description = 'Clears fade in and out for selected sequences'

    direction: bpy.props.StringProperty('both')
    active_only: bpy.props.BoolProperty(False)

    def execute(self, context):
        bpy.ops.ed.undo_push()
        if self.active_only:
            sequences = [current_active(context)]
        else:
            sequences = current_selected(context)

        for sequence in sequences:
            fade_curve = get_fade_curve(context, sequence, create=False)
            #iterate through selected sequences and remove fades
            if fade_curve:
                if self.direction != 'both':
                    fades(fade_curve, sequence, 'set', self.direction, fade_length=0)
                else:
                    fades(fade_curve, sequence, 'set', 'in', fade_length=0)
                    fades(fade_curve, sequence, 'set', 'out', fade_length=0)
                #if sequence.type == 'SOUND':
                #    sequence.volume = 1
                #else:
                #    sequence.blend_alpha = 1

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

    type: bpy.props.StringProperty()

    def execute(self, context):
        sequences = current_sequences(context)

        #store a list of selected sequences since adding a crossfade destroys the selection
        selected_sequences = current_selected(context)
        active_sequence = current_active(context)

        for sequence in selected_sequences:
            if sequence.type != 'SOUND' and not hasattr(sequence, 'input_1'):
                bpy.ops.ed.undo_push()
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

    if not child_sequence.parent:
        return False
    sequences = current_sequences(bpy.context)
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
    bl_idname = "VSEQF_MT_quickparents_menu"
    bl_label = "Quick Parents"

    @classmethod
    def poll(cls, context):
        del context
        prefs = get_prefs()
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
                layout.label(text="     Parent: ")
                layout.label(text=parent.name)

            if len(children) > 0:
                #At least one child sequence is found, display them
                layout.separator()
                layout.label(text="     Children:")
                index = 0
                while index < len(children):
                    layout.label(text=children[index].name)
                    index = index + 1

        else:
            layout.label(text='No Sequence Selected')


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

    action: bpy.props.StringProperty()

    def execute(self, context):
        selected = current_selected(context)
        active = current_active(context)
        if not active:
            return {'CANCELLED'}

        bpy.ops.ed.undo_push()

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

    strip: bpy.props.StringProperty()

    def execute(self, context):
        sequences = current_sequences(context)
        for sequence in sequences:
            if sequence.name == self.strip:
                bpy.ops.ed.undo_push()
                clear_parent(sequence)
                break
        redraw_sequencers()
        return {'FINISHED'}


class VSEQFImport(bpy.types.Operator, ImportHelper):
    """Loads different types of files into the sequencer"""
    bl_idname = 'vseqf.import'
    bl_label = 'Import Strip'

    type: bpy.props.EnumProperty(
        name="Import Type",
        items=(('MOVIE', 'Movie', ""), ("IMAGE", "Image", "")),
        default='MOVIE')

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)

    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True)
    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        description="Start frame of the sequence strip",
        default=0)
    channel: bpy.props.IntProperty(
        name="Channel",
        description="Channel to place this strip into",
        default=1)
    replace_selection: bpy.props.BoolProperty(
        name="Replace Selection",
        description="Replace the current selection",
        default=True)
    sound: bpy.props.BoolProperty(
        name="Sound",
        description="Load sound with the movie",
        default=True)
    use_movie_framerate: bpy.props.BoolProperty(
        name="Use Movie Framerate",
        description="Use framerate from the movie to keep sound and video in sync",
        default=False)
    import_location: bpy.props.EnumProperty(
        name="Import At",
        description="Location to import strips at",
        items=(("IMPORT_FRAME", "Import At Frame", ""), ("INSERT_FRAME", "Insert At Frame", ""), ("CUT_INSERT", "Cut And Insert At Frame", ""), ("END", "Import At End", "")),
        default="IMPORT_FRAME")
    autoparent: bpy.props.BoolProperty(
        name="Auto-Parent A/V",
        description="Automatically parent audio strips to their movie strips",
        default=True)
    autoproxy: bpy.props.BoolProperty(
        name="Auto-Set Proxy",
        description="Automatically enable proxy settings",
        default=False)
    autogenerateproxy: bpy.props.BoolProperty(
        name="Auto-Generate Proxy",
        description="Automatically generate proxies for imported strips",
        default=False)
    use_placeholders: bpy.props.BoolProperty(
        name="Use Placeholders",
        description="Use placeholders for missing frames of the strip",
        default=False)
    length: bpy.props.IntProperty(
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
                row.label(text="Length: "+str(number_of_files))
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
        fps = get_fps(context.scene)
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
        dirname = os.path.dirname(bpy.path.abspath(self.filepath))
        bpy.ops.sequencer.select_all(action='DESELECT')
        if self.import_location in ['END', 'INSERT_FRAME', 'CUT_INSERT']:
            frame = end_frame
        else:
            frame = self.start_frame
        all_imported = []
        to_parent = []
        last_frame = context.scene.frame_current
        if self.type == 'MOVIE':
            #iterate through files and import them
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
                        moviestrip.channel = self.channel + 1  #Needed to get around a bug in blender. blah.
                        soundstrip.channel = self.channel
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
    bl_idname = "VSEQF_MT_quicksnaps_menu"
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

    type: bpy.props.StringProperty()

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
            fps = get_fps(scene)
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
                    if not parent or (parent not in selected) or self.type == 'selection_to_cursor':
                        all_sequences.append(sequence)
                        if sequence.select:
                            to_snap.append(sequence)
            else:
                to_snap = selected
                all_sequences = sequences
            if active:
                previous = find_close_sequence(all_sequences, active, 'previous', 'nooverlap', sounds=True)
                next_seq = find_close_sequence(all_sequences, active, 'next', 'nooverlap', sounds=True)
            else:
                previous = None
                next_seq = None
            to_check = []
            for sequence in to_snap:
                snap_type = self.type
                if not hasattr(sequence, 'input_1'):
                    moved = 0
                    to_check.append([sequence, sequence.frame_start, sequence.frame_final_start, sequence.frame_final_end])
                    if snap_type == 'selection_to_cursor':
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
                                snap_type = 'end_to_cursor'
                            else:
                                sequence.frame_final_start = frame
                        elif sequence.select_right_handle:
                            if frame <= sequence.frame_final_start:
                                snap_type = 'begin_to_cursor'
                            else:
                                sequence.frame_final_end = frame
                        else:
                            snap_type = 'begin_to_cursor'
                        if snap_type != 'begin_to_cursor':
                            #fix child edges
                            if parenting:
                                for child in children:
                                    if child.frame_final_start == original_left:
                                        to_check.append([child, child.frame_start, child.frame_final_start, child.frame_final_end])
                                        child.frame_final_start = sequence.frame_final_start
                                    if child.frame_final_end == original_right:
                                        to_check.append([child, child.frame_start, child.frame_final_start, child.frame_final_end])
                                        child.frame_final_end = sequence.frame_final_end

                    if snap_type == 'begin_to_cursor':
                        offset = sequence.frame_final_start - sequence.frame_start
                        new_start = (frame - offset)
                        moved = new_start - sequence.frame_start
                        sequence.frame_start = new_start
                    if snap_type == 'end_to_cursor':
                        offset = sequence.frame_final_start - sequence.frame_start
                        new_start = (frame - offset - sequence.frame_final_duration)
                        moved = new_start - sequence.frame_start
                        sequence.frame_start = new_start
                    if snap_type == 'sequence_to_previous':
                        if previous:
                            offset = sequence.frame_final_start - sequence.frame_start
                            new_start = (previous.frame_final_end - offset)
                            moved = new_start - sequence.frame_start
                            sequence.frame_start = new_start
                        else:
                            self.report({'WARNING'}, 'No Previous Sequence Found')
                    if snap_type == 'sequence_to_next':
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
                            fade_curve = get_fade_curve(context, sequence, create=False)
                            if fade_curve:
                                fade_in = fades(fade_curve, sequence, 'detect', 'in', fade_low_point_frame=old_start)
                                if fade_in > 0:
                                    fades(fade_curve, sequence, 'set', 'in', fade_length=fade_in)
                        if old_end != sequence.frame_final_end:
                            # fix fade out
                            fade_curve = get_fade_curve(context, sequence, create=False)
                            if fade_curve:
                                fade_out = fades(fade_curve, sequence, 'detect', 'out', fade_low_point_frame=old_end)
                                if fade_out > 0:
                                    fades(fade_curve, sequence, 'set', 'out', fade_length=fade_out)
        return{'FINISHED'}


#Functions and classes related to QuickMarkers
def draw_quickmarker_menu(self, context):
    """Draws the submenu for the QuickMarker presets, placed in the sequencer markers menu"""
    layout = self.layout
    if len(context.scene.vseqf.marker_presets) > 0:
        layout.menu('VSEQF_MT_quickmarkers_menu', text="Quick Markers")


class VSEQF_PT_QuickMarkersPanel(bpy.types.Panel):
    """Panel for QuickMarkers operators and properties"""
    bl_label = "Quick Markers"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
        return prefs.markers

    def draw(self, context):
        scene = context.scene
        vseqf = scene.vseqf
        layout = self.layout

        row = layout.row()
        split = row.split(factor=.9, align=True)
        split.prop(vseqf, 'current_marker')
        split.operator('vseqf.quickmarkers_add_preset', text="", icon="PLUS").preset = vseqf.current_marker
        row = layout.row()
        row.template_list("VSEQF_UL_QuickMarkerPresetList", "", vseqf, 'marker_presets', vseqf, 'marker_index', rows=2)
        row = layout.row()
        row.prop(vseqf, 'marker_deselect', toggle=True)
        row = layout.row()
        row.label(text="Marker List:")
        row = layout.row()
        row.template_list("VSEQF_UL_QuickMarkerList", "", scene, "timeline_markers", scene.vseqf, "marker_index", rows=4)


class VSEQF_UL_QuickMarkerPresetList(bpy.types.UIList):
    """Draws an editable list of QuickMarker presets"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(factor=.9, align=True)
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


class VSEQF_UL_QuickMarkerList(bpy.types.UIList):
    """Draws an editable list of current markers in the timeline"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del data, icon, active_data, active_propname
        timecode = timecode_from_frames(item.frame, get_fps(context.scene), levels=0, subsecond_type='frames')
        split = layout.split(factor=.9, align=True)
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

    frame: bpy.props.IntProperty()

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

    frame: bpy.props.IntProperty()

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

    marker_name: bpy.props.StringProperty(name='Marker Name')

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

    frame: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        scene.frame_current = self.frame
        return{'FINISHED'}


class VSEQFQuickMarkersMenu(bpy.types.Menu):
    """Menu for adding QuickMarkers to the current frame of the timeline"""
    bl_idname = "VSEQF_MT_quickmarkers_menu"
    bl_label = "Quick Markers"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()
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

    marker: bpy.props.StringProperty()

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
    marker: bpy.props.StringProperty()

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

    preset: bpy.props.StringProperty()

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


#Functions and classes related to QuickTags
def populate_selected_tags():
    vseqf = bpy.context.scene.vseqf
    selected_sequences = current_selected(bpy.context)
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
    try:
        tags.clear()
    except:
        pass
    add_tags = sorted(temp_tags)
    for tag in add_tags:
        new_tag = tags.add()
        new_tag.text = tag


class VSEQFQuickTagsMenu(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_quicktags_menu'
    bl_label = "Tags"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()

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


class VSEQF_PT_QuickTagsPanel(bpy.types.Panel):
    """Panel for displaying, removing and adding tags"""

    bl_label = "Quick Tags"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()

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
        row.label(text='All Tags:')
        row = layout.row()
        row.template_list("VSEQF_UL_QuickTagListAll", "", vseqf, 'tags', vseqf, 'marker_index')
        row = layout.row()
        row.separator()

        row = layout.row()
        row.label(text='Edit Tags:')
        row = layout.row()
        row.prop(vseqf, 'show_tags', expand=True)
        if vseqf.show_tags == 'SELECTED':
            populate_selected_tags()
            row = layout.row()
            row.template_list("VSEQF_UL_QuickTagList", "", vseqf, 'selected_tags', vseqf, 'marker_index', rows=2)
            row = layout.row()
            split = row.split(factor=.9, align=True)
            split.prop(vseqf, 'current_tag', text='New Tag')
            split.operator('vseqf.quicktags_add', text="", icon="PLUS").text = vseqf.current_tag
            row = layout.row()
            row.operator('vseqf.quicktags_clear', text='Clear Selected Strip Tags').mode = 'selected'
        else:
            row = layout.row()
            row.template_list("VSEQF_UL_QuickTagList", "", sequence, 'tags', vseqf, 'marker_index', rows=2)
            row = layout.row()
            split = row.split(factor=.9, align=True)
            split.prop(vseqf, 'current_tag', text='New Tag')
            split.operator('vseqf.quicktags_add_active', text="", icon="PLUS").text = vseqf.current_tag
            #row = layout.row()
            #row.operator('vseqf.quicktags_add_marker', text='Add Marker Tag').marker = str(scene.frame_current)+','+vseqf.current_tag
            row = layout.row()
            row.operator('vseqf.quicktags_clear', text='Clear Active Strip Tags').mode = 'active'


class VSEQF_UL_QuickTagListAll(bpy.types.UIList):
    """Draws a list of tags"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(factor=.9, align=True)
        split.operator('vseqf.quicktags_select', text=item.text).text = item.text
        split.operator('vseqf.quicktags_add', text='', icon="PLUS").text = item.text

    def draw_filter(self, context, layout):
        pass


class VSEQF_UL_QuickTagList(bpy.types.UIList):
    """Draws an editable list of tags"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(factor=.9, align=True)
        display_text = item.text
        if item.use_offset:
            display_text = display_text + '(' + str(item.offset) + ')'
        split.operator('vseqf.quicktags_select', text=display_text).text = item.text
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

    mode: bpy.props.StringProperty('selected')

    def execute(self, context):
        if self.mode == 'selected':
            sequences = current_selected(context)
            if not sequences:
                return {'FINISHED'}
            bpy.ops.ed.undo_push()
            for sequence in sequences:
                sequence.tags.clear()
            populate_selected_tags()
            populate_tags()
        else:
            sequence = current_active(context)
            if not sequence:
                return {'FINISHED'}
            bpy.ops.ed.undo_push()
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

    text: bpy.props.StringProperty()

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

    tag: bpy.props.StringProperty()

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

    text: bpy.props.StringProperty()

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
        populate_selected_tags()
        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsAddMarker(bpy.types.Operator):
    """Adds a marker tag with the given text to the active sequence"""
    bl_idname = 'vseqf.quicktags_add_marker'
    bl_label = 'VSEQF Quick Tags Add Marker'
    bl_description = 'Add this marker tag to active sequence.'

    marker: bpy.props.StringProperty()

    def execute(self, context):
        marker = self.marker.replace("\n", '')
        frame, text = marker.split(',', 1)
        frame = int(frame)
        if text:
            bpy.ops.ed.undo_push()
            sequence = current_active(context)
            marker_frame = frame - sequence.frame_start
            tag_found = False
            for tag in sequence.tags:
                if tag.text == text:
                    tag_found = True
            if not tag_found:
                tag = sequence.tags.add()
                tag.text = text
                tag.use_offset = True
                tag.offset = marker_frame

            populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsAdd(bpy.types.Operator):
    """Adds a tag with the given text to the selected sequences
    Argument:
        text: String, tag to add"""
    bl_idname = 'vseqf.quicktags_add'
    bl_label = 'VSEQF Quick Tags Add'
    bl_description = 'Add this tag to all selected sequences'

    text: bpy.props.StringProperty()

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


class VSEQFQuickTagsAddActive(bpy.types.Operator):
    """Adds a tag with the given text to the active sequence
    Argument:
        text: String, tag to add"""
    bl_idname = 'vseqf.quicktags_add_active'
    bl_label = 'VSEQF Quick Tags Add'
    bl_description = 'Add this tag to the active sequence'

    text: bpy.props.StringProperty()

    def execute(self, context):
        text = self.text.replace("\n", '')
        if text:
            bpy.ops.ed.undo_push()
            sequence = current_active(context)
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
    #Check parenting settings, remove if parent strip doesnt exist (prevents cut strips from getting false parents)
    parent = find_parent(sequence)
    if not parent:
        sequence.parent = ''

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
    use_frame: bpy.props.BoolProperty(default=False)
    type: bpy.props.EnumProperty(name='Type', items=[("SOFT", "Soft", "", 1), ("HARD", "Hard", "", 2), ("INSERT", "Insert Cut", "", 3), ("INSERT_ONLY", "Insert Only", "", 4), ("TRIM", "Trim", "", 5), ("TRIM_LEFT", "Trim Left", "", 6), ("TRIM_RIGHT", "Trim Right", "", 7), ("SLIDE", "Slide", "", 8), ("SLIDE_LEFT", "Slide Left", "", 9), ("SLIDE_RIGHT", "Slide Right", "", 10), ("RIPPLE", "Ripple", "", 11), ("RIPPLE_LEFT", "Ripple Left", "", 12), ("RIPPLE_RIGHT", "Ripple Right", "", 13), ("UNCUT", "UnCut", "", 14), ("UNCUT_LEFT", "UnCut Left", "", 15), ("UNCUT_RIGHT", "UnCut Right", "", 16)], default='SOFT')
    side: bpy.props.EnumProperty(name='Side', items=[("BOTH", "Both", "", 1), ("RIGHT", "Right", "", 2), ("LEFT", "Left", "", 3)], default='BOTH')
    all: bpy.props.BoolProperty(name='Cut All', default=False)
    use_all: bpy.props.BoolProperty(default=False)
    insert: bpy.props.IntProperty(0)
    use_insert: bpy.props.BoolProperty(default=False)

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
        return self.start_cut(context)

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
        return self.start_cut(context, side)

    def uncut(self, context, side="BOTH"):
        #merges a sequence to the one on the left or right if they share the same source and position
        if side == 'BOTH':
            self.reset()
            return{"CANCELLED"}

        selected = current_selected(context)
        to_uncut = []
        for sequence in selected:
            if not sequence.lock and not hasattr(sequence, 'input_1'):
                to_uncut.append(sequence)
        for sequence in to_uncut:
            if side == 'LEFT':
                direction = 'previous'
            else:
                direction = 'next'
            sequences = current_sequences(context)
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
        self.reset()
        return{'FINISHED'}

    def start_cut(self, context, side="BOTH"):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            self.reset()
            return{'CANCELLED'}
        bpy.ops.ed.undo_push()
        if not self.use_all:
            self.all = context.scene.vseqf.quickcuts_all
        if self.type == 'UNCUT_LEFT':
            return self.uncut(context, side='LEFT')
        if self.type == 'UNCUT_RIGHT':
            return self.uncut(context, side='RIGHT')
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
        cut_pairs = []

        #determine all sequences available to cut
        to_cut_temp = []
        for sequence in sequences:
            if not sequence.lock and under_cursor(sequence, self.frame) and not hasattr(sequence, 'input_1'):
                if self.all:
                    to_cut.append(sequence)
                    to_cut_temp.append(sequence)
                elif sequence.select:
                    to_cut.append(sequence)
                    to_cut_temp.append(sequence)
                    if vseqf_parenting():
                        children = get_recursive(sequence, [])
                        for child in children:
                            if not child.lock and (not hasattr(child, 'input_1')) and child not in to_cut:
                                to_cut.append(child)

        #find the ripple amount
        ripple_amount = 0
        for sequence in to_cut_temp:
            if side == 'LEFT':
                cut_amount = self.frame - sequence.frame_final_start
            else:
                cut_amount = sequence.frame_final_end - self.frame
            #to_cut.append(sequence)
            if cut_amount > ripple_amount:
                ripple_amount = cut_amount

        if side == 'LEFT':
            ripple_frame = self.frame - ripple_amount
        else:
            ripple_frame = self.frame

        bpy.ops.sequencer.select_all(action='DESELECT')
        to_cut.sort(key=lambda x: x.frame_final_start)
        for sequence in to_cut:
            cutable = under_cursor(sequence, self.frame)
            left = False
            right = False
            if self.type in ['TRIM', 'SLIDE', 'RIPPLE']:
                if side != 'BOTH':
                    if side == 'LEFT':
                        if cutable:
                            sequence.frame_final_start = self.frame
                        to_select.append(sequence)
                        if self.type == 'SLIDE':
                            sequence.frame_start = sequence.frame_start - ripple_amount
                    else:
                        if cutable:
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
                if cutable:
                    left, right = vseqf_cut(sequence=sequence, frame=self.frame, cut_type=cut_type)
                    cut_pairs.append([left, right])
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
            if right and left:
                children = find_children(left)
                for child in children:
                    if child.frame_final_start >= right.frame_final_start:
                        child.parent = right.name

        #ripple/insert
        if self.type == 'INSERT' or self.type == 'RIPPLE' or self.type == 'INSERT_ONLY':
            if self.type == 'RIPPLE':
                insert = 0 - ripple_amount
            else:
                if self.use_insert:
                    insert = self.insert
                else:
                    insert = context.scene.vseqf.quickcuts_insert
            sequences = current_sequences(context)
            ripple_timeline(sequences, ripple_frame - 1, insert)
        else:
            for sequence in to_select:
                if sequence:
                    sequence.select = True
        if to_active:
            context.scene.sequence_editor.active_strip = to_active
        if side == 'LEFT':
            if self.type in ['RIPPLE', 'SLIDE']:
                context.scene.frame_current = context.scene.frame_current - ripple_amount
        else:
            if self.type in ['SLIDE']:
                context.scene.frame_current = context.scene.frame_current + ripple_amount
        self.reset()
        return{'FINISHED'}


class VSEQFQuickTimelineMenu(bpy.types.Menu):
    bl_idname = "VSEQF_MT_quicktimeline_menu"
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

    bl_idname = "VSEQF_MT_quickcuts_menu"
    bl_label = "Quick Cuts"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()

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


class VSEQF_PT_QuickCutsPanel(bpy.types.Panel):
    """Panel for QuickCuts operators and properties"""

    bl_label = "Quick Cuts"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = get_prefs()

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
        split = row.split(factor=.5, align=True)
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
        split = row.split(factor=.5, align=True)
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

    ripple: bpy.props.BoolProperty(default=False)

    def reset(self):
        self.ripple = False

    def execute(self, context):
        bpy.ops.ed.undo_push()
        to_delete = current_selected(context)
        if not to_delete:
            return {'CANCELLED'}

        #Determine frames that need to be rippled
        ripple_frames = set()
        for deletable in to_delete:
            delete_start = deletable.frame_final_start
            delete_end = deletable.frame_final_end
            for frame in range(delete_start, delete_end+1):
                ripple_frames.add(frame)

        #Delete selected
        for sequence in to_delete:
            if vseqf_parenting() and context.scene.vseqf.delete_children:
                children = find_children(sequence)
                for child in children:
                    if child not in to_delete:
                        child.select = True
        bpy.ops.sequencer.delete()

        if self.ripple:
            #Ripple remaining sequences
            sequences = current_sequences(context)
            ripple_frames = list(ripple_frames)
            ripple_frames.sort()
            start_frame = ripple_frames[0]
            end_frame = ripple_frames[0]
            ripple_frames.append(ripple_frames[-1]+2)
            for frame in ripple_frames:
                if frame - end_frame > 1:
                    #Ripple section, start next section
                    ripple_length = end_frame - start_frame
                    ripple_timeline(sequences, start_frame, -ripple_length)
                    start_frame = frame
                end_frame = frame
            context.scene.frame_current = ripple_frames[0]
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

    operation: bpy.props.StringProperty()

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
    text: bpy.props.StringProperty(
        name="Tag Text",
        default="")
    use_offset: bpy.props.BoolProperty(
        name="Use Frame Offset",
        default=False)
    offset: bpy.props.IntProperty(
        name="Frame Offset",
        default=0)


class VSEQFMarkerPreset(bpy.types.PropertyGroup):
    """Property for marker presets"""
    text: bpy.props.StringProperty(name="Text", default="")


class VSEQFSettingsMenu(bpy.types.Menu):
    """Pop-up menu for settings related to QuickContinuous"""
    bl_idname = "VSEQF_MT_settings_menu"
    bl_label = "Quick Settings"

    def draw(self, context):
        prefs = get_prefs()

        layout = self.layout
        scene = context.scene
        layout.prop(scene.vseqf, 'grab_multiselect')
        layout.prop(scene.vseqf, 'snap_cursor_to_edge')
        layout.prop(scene.vseqf, 'snap_new_end')
        if prefs.parenting:
            layout.separator()
            layout.label(text='QuickParenting Settings')
            layout.separator()
            layout.prop(scene.vseqf, 'children')
            layout.prop(scene.vseqf, 'delete_children')
            layout.prop(scene.vseqf, 'autoparent')
            layout.prop(scene.vseqf, 'select_children')
        if prefs.proxy:
            layout.separator()
            layout.label(text='QuickProxy Settings')
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
    name: bpy.props.StringProperty(name="Preset Name", default="")
    left: bpy.props.FloatProperty(name="Leftmost Visible Frame", default=0.0)
    right: bpy.props.FloatProperty(name="Rightmost Visible Frame", default=300.0)
    bottom: bpy.props.FloatProperty(name="Bottom Visible Channel", default=0.0)
    top: bpy.props.FloatProperty(name="Top Visible Channel", default=5.0)


class VSEQFQuick3PointValues(bpy.types.PropertyGroup):
    full_length: bpy.props.IntProperty(
        default=1,
        min=0)
    import_frame_in: bpy.props.IntProperty(
        default=-1,
        min=-1)
    import_frame_length: bpy.props.IntProperty(
        default=-1,
        min=-1)
    import_minutes_in: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_minutes_in)
    import_seconds_in: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_seconds_in)
    import_frames_in: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_frames_in)
    import_minutes_length: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_minutes_length)
    import_seconds_length: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_seconds_length)
    import_frames_length: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_frames_length)


class VSEQFSetting(bpy.types.PropertyGroup):
    """Property group to store most VSEQF settings.  This will be assigned to scene.vseqf"""
    zoom_presets: bpy.props.CollectionProperty(type=VSEQFZoomPreset)
    last_frame: bpy.props.IntProperty(
        name="Last Scene Frame",
        default=1)

    follow: bpy.props.BoolProperty(
        name="Cursor Following",
        default=False,
        update=start_follow)
    grab_multiselect: bpy.props.BoolProperty(
        name="Grab Multiple With Mouse",
        default=False,
        description="Allows the right-click drag grab to work with multiple strips.")

    children: bpy.props.BoolProperty(
        name="Cut/Move Children",
        default=True,
        description="Automatically cut and move child strips along with a parent.")
    autoparent: bpy.props.BoolProperty(
        name="Auto-Parent New Audio To Video",
        default=True,
        description="Automatically parent audio strips to video when importing a movie with both types of strips.")
    select_children: bpy.props.BoolProperty(
        name="Auto-Select Children",
        default=False,
        description="Automatically select child strips when a parent is selected.")
    expanded_children: bpy.props.BoolProperty(default=True)
    delete_children: bpy.props.BoolProperty(
        name="Auto-Delete Children",
        default=False,
        description="Automatically delete child strips when a parent is deleted.")

    transition: bpy.props.EnumProperty(
        name="Transition Type",
        default="CROSS",
        items=[("CROSS", "Crossfade", "", 1), ("WIPE", "Wipe", "", 2), ("GAMMA_CROSS", "Gamma Cross", "", 3)])
    fade: bpy.props.IntProperty(
        name="Fade Length",
        default=0,
        min=0,
        description="Default Fade Length In Frames")
    fadein: bpy.props.IntProperty(
        name="Fade In Length",
        default=0,
        min=0,
        description="Current Fade In Length In Frames")
    fadeout: bpy.props.IntProperty(
        name="Fade Out Length",
        default=0,
        min=0,
        description="Current Fade Out Length In Frames")

    enable_proxy: bpy.props.BoolProperty(
        name="Enable Proxy On Import",
        default=False)
    build_proxy: bpy.props.BoolProperty(
        name="Auto-Build Proxy On Import",
        default=False)
    proxy_25: bpy.props.BoolProperty(
        name="25%",
        default=True)
    proxy_50: bpy.props.BoolProperty(
        name="50%",
        default=False)
    proxy_75: bpy.props.BoolProperty(
        name="75%",
        default=False)
    proxy_100: bpy.props.BoolProperty(
        name="100%",
        default=False)
    proxy_quality: bpy.props.IntProperty(
        name="Quality",
        default=90,
        min=1,
        max=100)

    current_marker_frame: bpy.props.IntProperty(
        default=0)
    marker_index: bpy.props.IntProperty(
        name="Marker Display Index",
        default=0)
    marker_presets: bpy.props.CollectionProperty(
        type=VSEQFMarkerPreset)
    expanded_markers: bpy.props.BoolProperty(default=True)
    current_marker: bpy.props.StringProperty(
        name="New Preset",
        default='')
    marker_deselect: bpy.props.BoolProperty(
        name="Deselect New Markers",
        default=True)

    zoom_size: bpy.props.IntProperty(
        name='Zoom Amount',
        default=200,
        min=1,
        description="Zoom size in frames",
        update=zoom_cursor)
    step: bpy.props.IntProperty(
        name="Frame Step",
        default=0,
        min=-4,
        max=4)
    skip_index: bpy.props.IntProperty(
        default=0)

    current_tag: bpy.props.StringProperty(
        name="New Tag",
        default='')
    tags: bpy.props.CollectionProperty(type=VSEQFTags)
    selected_tags: bpy.props.CollectionProperty(type=VSEQFTags)
    show_tags: bpy.props.EnumProperty(
        name="Show Tags On",
        default='ACTIVE',
        items=[('ACTIVE', 'Active Strip', '', 1), ('SELECTED', 'Selected Strips', '', 2)])
    show_selected_tags: bpy.props.BoolProperty(
        name="Show Tags For All Selected Sequences",
        default=False)

    quickcuts_insert: bpy.props.IntProperty(
        name="Frames To Insert",
        default=0,
        min=0)
    quickcuts_all: bpy.props.BoolProperty(
        name='Cut All Sequences',
        default=False,
        description='Cut all sequences, regardless of selection (not including locked sequences)')
    snap_new_end: bpy.props.BoolProperty(
        name='Snap Cursor To End Of New Sequences',
        default=False)
    snap_cursor_to_edge: bpy.props.BoolProperty(
        name='Snap Cursor When Dragging Edges',
        default=False)


class VSEQuickFunctionSettings(bpy.types.AddonPreferences):
    """Addon preferences for QuickFunctions, used to enable and disable features"""
    bl_idname = __name__
    parenting: bpy.props.BoolProperty(
        name="Enable Quick Parenting",
        default=True)
    fades: bpy.props.BoolProperty(
        name="Enable Quick Fades",
        default=True)
    proxy: bpy.props.BoolProperty(
        name="Enable Quick Proxy",
        default=True)
    markers: bpy.props.BoolProperty(
        name="Enable Quick Markers",
        default=True)
    tags: bpy.props.BoolProperty(
        name="Enable Quick Tags",
        default=True)
    cuts: bpy.props.BoolProperty(
        name="Enable Quick Cuts",
        default=True)
    edit: bpy.props.BoolProperty(
        name="Enable Compact Edit Panel",
        default=False)
    threepoint: bpy.props.BoolProperty(
        name="Enable Quick Three Point",
        default=True)

    def draw(self, context):
        del context
        layout = self.layout
        layout.prop(self, "parenting")
        layout.prop(self, "fades")
        layout.prop(self, "proxy")
        layout.prop(self, "markers")
        layout.prop(self, "tags")
        layout.prop(self, "cuts")
        layout.prop(self, "edit")
        layout.prop(self, "threepoint")


class VSEQFTempSettings(object):
    """Substitute for the addon preferences when this script isn't loaded as an addon"""
    parenting = True
    fades = True
    proxy = True
    markers = True
    tags = True
    cuts = True
    edit = True
    threepoint = True


#Replaced Blender Menus
class VSEQFDeleteConfirm(bpy.types.Menu):
    bl_idname = "VSEQF_MT_delete_menu"
    bl_label = "Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete')


class VSEQFDeleteRippleConfirm(bpy.types.Menu):
    bl_idname = "VSEQF_MT_delete_ripple_menu"
    bl_label = "Ripple Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete').ripple = True


class SEQUENCER_MT_strip_transform(bpy.types.Menu):
    bl_label = "Transform"

    def draw(self, context):
        layout = self.layout

        #layout.operator("transform.transform", text="Move").mode = 'TRANSLATION'
        layout.operator("vseqf.grab", text="Grab/Move")
        #layout.operator("transform.transform", text="Move/Extend from Frame").mode = 'TIME_EXTEND'
        layout.operator("vseqf.grab", text="Grab/Extend from frame").mode = 'TIME_EXTEND'
        #layout.operator("sequencer.slip", text="Slip Strip Contents")
        layout.operator("vseqf.grab", text="Slip Strip Contents").mode = 'SLIP'

        layout.separator()
        layout.operator_menu_enum("sequencer.swap", "side")

        layout.separator()
        layout.operator("sequencer.gap_remove").all = False
        layout.operator("sequencer.gap_insert")

        layout.separator()
        layout.operator('vseqf.quicksnaps', text='Snap Beginning To Cursor').type = 'begin_to_cursor'
        layout.operator('vseqf.quicksnaps', text='Snap End To Cursor').type = 'end_to_cursor'
        layout.operator('vseqf.quicksnaps', text='Snap To Previous Strip').type = 'sequence_to_previous'
        layout.operator('vseqf.quicksnaps', text='Snap To Next Strip').type = 'sequence_to_next'


class SEQUENCER_MT_strip(bpy.types.Menu):
    bl_label = "Strip"

    def draw(self, context):
        layout = self.layout

        layout.operator_context = 'INVOKE_REGION_WIN'

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_transform")

        layout.separator()
        #layout.operator("sequencer.cut", text="Cut").type = 'SOFT'
        #layout.operator("sequencer.cut", text="Hold Cut").type = 'HARD'
        layout.operator("vseqf.cut", text="Cut").type = 'SOFT'
        layout.operator("vseqf.cut", text="Hold Cut").type = 'HARD'

        layout.separator()
        layout.operator("sequencer.copy", text="Copy")
        layout.operator("sequencer.paste", text="Paste")
        layout.operator("sequencer.duplicate_move")
        layout.operator("sequencer.delete", text="Delete...")

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_lock_mute")

        #strip = act_strip(context)
        strip = current_active(context)

        if strip:
            stype = strip.type

            if stype != 'SOUND':
                layout.separator()
                layout.operator_menu_enum("sequencer.strip_modifier_add", "type", text="Add Modifier")
                layout.operator("sequencer.strip_modifier_copy", text = "Copy Modifiers to Selection")

            if stype in {
                    'CROSS', 'ADD', 'SUBTRACT', 'ALPHA_OVER', 'ALPHA_UNDER',
                    'GAMMA_CROSS', 'MULTIPLY', 'OVER_DROP', 'WIPE', 'GLOW',
                    'TRANSFORM', 'COLOR', 'SPEED', 'MULTICAM', 'ADJUSTMENT',
                    'GAUSSIAN_BLUR', 'TEXT',
            }:
                layout.separator()
                layout.operator_menu_enum("sequencer.change_effect_input", "swap")
                layout.operator_menu_enum("sequencer.change_effect_type", "type")
                layout.operator("sequencer.reassign_inputs")
                layout.operator("sequencer.swap_inputs")
            elif stype in {'IMAGE', 'MOVIE'}:
                layout.separator()
                layout.operator("sequencer.rendersize")
                layout.operator("sequencer.images_separate")
                layout.operator("sequencer.deinterlace_selected_movies")
            elif stype == 'META':
                layout.separator()
                layout.operator("sequencer.meta_separate")

        layout.separator()
        #layout.operator("sequencer.meta_make")
        layout.operator("vseqf.meta_make")
        layout.operator("sequencer.meta_toggle", text="Toggle Meta")

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_input")

        layout.separator()
        layout.operator("sequencer.rebuild_proxy")


def sel_sequences(context):
    try:
        return len(context.selected_sequences) if context.selected_sequences else 0
    except AttributeError:
        return 0


class SEQUENCER_MT_add(bpy.types.Menu):
    bl_label = "Add"

    def draw(self, context):

        layout = self.layout
        layout.operator_context = 'INVOKE_REGION_WIN'

        if len(bpy.data.scenes) > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.scene_strip_add", text="Scene...", icon='SCENE_DATA')
        elif len(bpy.data.scenes) > 1:
            layout.operator_menu_enum("sequencer.scene_strip_add", "scene", text="Scene", icon='SCENE_DATA')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Scene", icon='SCENE_DATA')

        if len(bpy.data.movieclips) > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.movieclip_strip_add", text="Clip...", icon='TRACKER')
        elif len(bpy.data.movieclips) > 1:
            layout.operator_menu_enum("sequencer.movieclip_strip_add", "clip", text="Clip", icon='TRACKER')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Clip", icon='TRACKER')

        if len(bpy.data.masks) > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.mask_strip_add", text="Mask...", icon='MOD_MASK')
        elif len(bpy.data.masks) > 1:
            layout.operator_menu_enum("sequencer.mask_strip_add", "mask", text="Mask", icon='MOD_MASK')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Mask", icon='MOD_MASK')

        layout.separator()

        #layout.operator("sequencer.movie_strip_add", text="Movie", icon='FILE_MOVIE')
        layout.operator("vseqf.import", text="Movie", icon="FILE_MOVIE").type = 'MOVIE'
        layout.operator("sequencer.sound_strip_add", text="Sound", icon='FILE_SOUND')
        #layout.operator("sequencer.image_strip_add", text="Image/Sequence", icon='FILE_IMAGE')
        layout.operator("vseqf.import", text="Image/Sequence", icon="FILE_IMAGE").type = 'IMAGE'

        layout.separator()

        layout.operator_context = 'INVOKE_REGION_WIN'
        layout.operator("sequencer.effect_strip_add", text="Color", icon='COLOR').type = 'COLOR'
        layout.operator("sequencer.effect_strip_add", text="Text", icon='FONT_DATA').type = 'TEXT'

        layout.separator()

        layout.operator("sequencer.effect_strip_add", text="Adjustment Layer", icon='COLOR').type = 'ADJUSTMENT'

        layout.operator_context = 'INVOKE_DEFAULT'
        layout.menu("SEQUENCER_MT_add_effect", icon='SHADERFX')

        col = layout.column()
        col.menu("SEQUENCER_MT_add_transitions", icon='ARROW_LEFTRIGHT')
        col.enabled = sel_sequences(context) >= 2


#Register properties, operators, menus and shortcuts
classes = (SEQUENCER_MT_add, SEQUENCER_MT_strip, SEQUENCER_MT_strip_transform, VSEQFAddZoom, VSEQFClearZooms, VSEQF_PT_CompactEdit, VSEQFContextCursor,
           VSEQFContextMarker, VSEQFContextNone, VSEQFContextSequence, VSEQFContextSequenceLeft, VSEQFDoubleUndo,
           VSEQFContextSequenceRight, VSEQFCut, VSEQFDelete, VSEQFDeleteConfirm, VSEQFDeleteRippleConfirm,
           VSEQFFollow, VSEQFGrab, VSEQFGrabAdd, VSEQFImport, VSEQFMarkerPreset, VSEQFMeta, VSEQFQuickCutsMenu,
           VSEQF_PT_QuickCutsPanel, VSEQFQuickFadesClear, VSEQFModalFades, VSEQFContextMenu,
           VSEQFQuickFadesCross, VSEQFQuickFadesMenu, VSEQF_PT_QuickFadesPanel, VSEQFQuickFadesSet,
           VSEQFQuickMarkerDelete, VSEQFQuickMarkerJump,
           VSEQF_UL_QuickMarkerList, VSEQFQuickMarkerMove, VSEQF_UL_QuickMarkerPresetList, VSEQFQuickMarkerRename,
           VSEQFQuickMarkersAddPreset, VSEQFQuickMarkersMenu, VSEQF_PT_QuickMarkersPanel, VSEQFQuickMarkersPlace,
           VSEQFQuickMarkersRemovePreset, VSEQFQuickParents, VSEQFQuickParentsClear, VSEQFQuickParentsMenu,
           VSEQFQuickSnaps, VSEQFQuickSnapsMenu, VSEQF_UL_QuickTagList, VSEQF_UL_QuickTagListAll, VSEQFQuickTagsAdd,
           VSEQFQuickTagsAddActive, VSEQFQuickTagsAddMarker,
           VSEQFQuickTagsClear, VSEQFQuickTagsMenu, VSEQF_PT_QuickTagsPanel, VSEQFQuickTagsRemove, VSEQFQuickTagsRemoveFrom,
           VSEQFQuickTagsSelect, VSEQFQuickTimeline, VSEQFQuickTimelineMenu, VSEQFQuickZoomPreset,
           VSEQFQuickZoomPresetMenu, VSEQFQuickZooms, VSEQFQuickZoomsMenu, VSEQFRemoveZoom, VSEQFSelectGrab,
           VSEQFSettingsMenu, VSEQFTags, VSEQF_PT_ThreePointBrowserPanel, VSEQFThreePointImport,
           VSEQFThreePointImportToClip, VSEQFThreePointOperator, VSEQF_PT_ThreePointPanel, VSEQFZoomPreset,
           VSEQFQuickShortcutsNudge, VSEQFQuickShortcutsSpeed, VSEQFQuickShortcutsSkip, VSEQFQuickShortcutsResetPlay,
           VSEQFQuick3PointValues, VSEQFSetting, VSEQFMetaExit, VSEQF_PT_Parenting)


def register():
    bpy.utils.register_class(VSEQuickFunctionSettings)

    #Register classes
    for cls in classes:
        bpy.utils.register_class(cls)

    global vseqf_draw_handler
    if vseqf_draw_handler:
        try:
            bpy.types.SpaceSequenceEditor.draw_handler_remove(vseqf_draw_handler, 'WINDOW')
        except:
            pass
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
        if (keymapitem.type == 'Z') | (keymapitem.type == 'F') | (keymapitem.type == 'S') | (keymapitem.type == 'G') | (keymapitem.type == 'W') | (keymapitem.type == 'LEFTMOUSE') | (keymapitem.type == 'RIGHTMOUSE') | (keymapitem.type == 'K') | (keymapitem.type == 'E') | (keymapitem.type == 'X') | (keymapitem.type == 'DEL') | (keymapitem.type == 'M'):
            keymapitems.remove(keymapitem)
    keymapmarker = keymapitems.new('wm.call_menu', 'M', 'PRESS', alt=True)
    keymapmarker.properties.name = 'VSEQF_MT_quickmarkers_menu'
    keymapitems.new('vseqf.meta_make', 'G', 'PRESS', ctrl=True)
    keymapzoom = keymapitems.new('wm.call_menu', 'Z', 'PRESS')
    keymapzoom.properties.name = 'VSEQF_MT_quickzooms_menu'
    keymapitems.new('vseqf.modal_fades', 'F', 'PRESS')
    keymapfademenu = keymapitems.new('wm.call_menu', 'F', 'PRESS', shift=True)
    keymapfademenu.properties.name = 'VSEQF_MT_quickfades_menu'
    keymapsnap = keymapitems.new('wm.call_menu', 'S', 'PRESS')
    keymapsnapto = keymapitems.new('vseqf.quicksnaps', 'S', 'PRESS', shift=True)
    keymapsnapto.properties.type = 'selection_to_cursor'
    keymapsnap.properties.name = 'VSEQF_MT_quicksnaps_menu'
    keymapparent = keymapitems.new('wm.call_menu', 'P', 'PRESS', ctrl=True)
    keymapparent.properties.name = 'VSEQF_MT_quickparents_menu'
    keymapparentselect = keymapitems.new('vseqf.quickparents', 'P', 'PRESS', shift=True)
    keymapparentselect.properties.action = 'select_children'

    keymapcuts = keymapitems.new('wm.call_menu', 'K', 'PRESS', ctrl=True)
    keymapcuts.properties.name = 'VSEQF_MT_quickcuts_menu'
    keymapitems.new('vseqf.cut', 'K', 'PRESS')
    keymapcuthard = keymapitems.new('vseqf.cut', 'K', 'PRESS', shift=True)
    keymapcuthard.properties.type = 'HARD'
    keymapcutripple = keymapitems.new('vseqf.cut', 'K', 'PRESS', alt=True)
    keymapcutripple.properties.type = 'RIPPLE'
    keymapcuttrim = keymapitems.new('vseqf.cut', 'K', 'PRESS', alt=True, shift=True)
    keymapcuttrim.properties.type = 'TRIM'

    keymapitems.new('vseqf.grab', 'G', 'PRESS')
    keymapitems.new('vseqf.context_menu', 'ACCENT_GRAVE', 'PRESS')
    keymapitems.new('vseqf.context_menu', 'W', 'PRESS')
    keymapitems.new('vseqf.select_grab', 'LEFTMOUSE', 'PRESS')
    keymapitems.new('vseqf.select_grab', 'RIGHTMOUSE', 'PRESS')

    keymapgrabextend = keymapitems.new('vseqf.grab', 'E', 'PRESS')
    keymapgrabextend.properties.mode = 'TIME_EXTEND'
    keymapslip = keymapitems.new('vseqf.grab', 'S', 'PRESS', alt=True)
    keymapslip.properties.mode = 'SLIP'
    keymapdelete1 = keymapitems.new('wm.call_menu', 'X', 'PRESS')
    keymapdelete1.properties.name = 'VSEQF_MT_delete_menu'
    keymapdelete2 = keymapitems.new('wm.call_menu', 'DEL', 'PRESS')
    keymapdelete2.properties.name = 'VSEQF_MT_delete_menu'
    keymapdelete3 = keymapitems.new('wm.call_menu', 'X', 'PRESS', alt=True)
    keymapdelete3.properties.name = 'VSEQF_MT_delete_ripple_menu'
    keymapdelete4 = keymapitems.new('wm.call_menu', 'DEL', 'PRESS', alt=True)
    keymapdelete4.properties.name = 'VSEQF_MT_delete_ripple_menu'

    #QuickShortcuts Shortcuts
    keymapitems.new('vseqf.cut', 'NUMPAD_0', 'PRESS')
    keymapitem = keymapitems.new('wm.call_menu', 'NUMPAD_0', 'PRESS', ctrl=True)
    keymapitem.properties.name = 'VSEQF_MT_quickcuts_menu'
    keymapitem = keymapitems.new('vseqf.cut', 'NUMPAD_0', 'PRESS', alt=True)
    keymapitem.properties.type = 'RIPPLE'
    keymapitem = keymapitems.new('vseqf.cut', 'NUMPAD_0', 'PRESS', shift=True)
    keymapitem.properties.type = 'HARD'
    keymapitem = keymapitems.new('vseqf.cut', 'NUMPAD_0', 'PRESS', alt=True, shift=True)
    keymapitem.properties.type = 'TRIM'

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
    handlers = bpy.app.handlers.depsgraph_update_post
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
    handlers = bpy.app.handlers.depsgraph_update_post
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
