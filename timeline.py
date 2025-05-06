import bpy
from . import vseqf


#Effect manipulation and cleanup
def effect_children(strip, to_check):
    effects = []
    for seq in to_check:
        if hasattr(seq, 'input_1'):
            if seq.input_1 == strip:
                effects.append(seq)
        if hasattr(seq, 'input_2'):
            if seq.input_2 == strip:
                effects.append(seq)
    return effects


def fix_effect(effect, apply_from, apply_to, to_check):
    #do whatever is needed to 'fix' the given effect and make it apply to the new strip
    sub_effects = effect_children(effect, to_check)
    if not hasattr(effect, 'input_2'):
        #just a one-input effect, just copy it to the new strip and check its children
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
    #copies a given single-input effect to the given strip
    old_selects = []
    strips = current_strips(bpy.context)
    for strip in strips:
        if strip.select:
            old_selects.append(strip)
            strip.select = False
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
    for strip in old_selects:
        strip.select = True
    return new_effect


def fix_effects(cut_pairs, strips):
    effects = []
    for strip in strips:
        if hasattr(strip, 'input_1'):
            effects.append(strip)
    for cut_pair in cut_pairs:
        left, right = cut_pair
        if left and right:
            left_effects = effect_children(left, effects)
            for effect in left_effects:
                fix_effect(effect, left, right, effects)


#Meta strip manipulations
def inside_meta_strip():
    try:
        if len(bpy.context.scene.sequence_editor.meta_stack) > 0:
            return True
    except:
        pass
    return False


class VSEQFMetaExit(bpy.types.Operator):
    bl_idname = 'vseqf.meta_exit'
    bl_label = 'Exit The Current Meta Strip'

    def execute(self, context):
        del context
        if inside_meta_strip():
            bpy.ops.sequencer.select_all(action='DESELECT')
            bpy.ops.sequencer.meta_toggle()
        return{'FINISHED'}


#Strip info functions
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
    selected = context.selected_strips
    if selected:
        return selected
    else:
        return []


def current_strips(context):
    strips = context.strips
    if strips:
        return strips
    else:
        return []


def find_strips_end(strips):
    end = 1
    for strip in strips:
        if strip.frame_final_end > end:
            end = strip.frame_final_end
    return end


def find_strips_start(strips):
    if not strips:
        return 1
    start = strips[0].frame_final_start
    for strip in strips:
        if strip.frame_final_start < start:
            start = strip.frame_final_start
    return start


def find_timeline_height(strips):
    height = 1
    for strip in strips:
        if strip.channel > height:
            height = strip.channel
    return height


def find_close_strip(strips, selected_strip, direction, mode='overlap', sounds=False, effects=True):
    """Finds the closest strip in one direction to the given strip
    Arguments:
        strips: List of strips to search through
        selected_strip: VSE Strip object that will be used as the basis for the search
        direction: String, must be 'next' or 'previous', determines the direction to search in
        mode: String, determines how the strips are searched
            'overlap': Only returns strips that overlap selected_strip
            'channel': Only returns strips that are in the same channel as selected_strip
            'simple': Just looks for the previous or next frame_final_start
            'nooverlap': Returns the previous strip, ignoring any that are overlapping
            <any other string>: All strips are returned
        sounds: Boolean, if False, 'SOUND' strip types are ignored
        effects: Boolean, if False, effect strips that are applied to another strip are ignored

    Returns: VSE Strip object, or Boolean False if no matching strip is found
    :rtype: bpy.types.Strip"""

    overlap_nexts = []
    overlap_previous = []
    nexts = []
    previous = []
    found = None

    if mode == 'simple':
        nexts = []
        previous = []
        for strip in strips:
            #don't bother with sound or effect type strips
            if (strip.type != 'SOUND') or sounds:
                #check if the strip is an effect of the selected strip, ignore if so
                if hasattr(strip, 'input_1'):
                    if strip.input_1 == selected_strip or not effects:
                        continue
                if strip.frame_final_start <= selected_strip.frame_final_start and strip != selected_strip:
                    previous.append(strip)
                elif strip.frame_final_start >= selected_strip.frame_final_start and strip != selected_strip:
                    nexts.append(strip)
        if direction == 'next':
            if len(nexts) > 0:
                found = min(nexts, key=lambda seq: (seq.frame_final_start - selected_strip.frame_final_start))
        else:
            if len(previous) > 0:
                found = min(previous, key=lambda seq: (selected_strip.frame_final_start - seq.frame_final_start))
    else:
        #iterate through strips to find all strips to one side of the selected strip
        for strip in strips:
            #don't bother with sound or effect type strips
            if (strip.type != 'SOUND') or sounds:
                #check if the strip is an effect of the selected strip, ignore if so
                if hasattr(strip, 'input_1'):
                    if strip.input_1 == selected_strip or not effects:
                        continue
                if strip.frame_final_start >= selected_strip.frame_final_end:
                    #current strip is after selected strip
                    if not (mode == 'channel' and selected_strip.channel != strip.channel):
                        #dont append if channel mode and strips are not on same channel
                        nexts.append(strip)
                elif strip.frame_final_end <= selected_strip.frame_final_start:
                    #current strip is before selected strip
                    if not (mode == 'channel' and selected_strip.channel != strip.channel):
                        #dont append if channel mode and strips are not on same channel
                        previous.append(strip)
                if (strip.frame_final_start > selected_strip.frame_final_start) & (strip.frame_final_start < selected_strip.frame_final_end) & (strip.frame_final_end > selected_strip.frame_final_end):
                    #current strip startpoint is overlapping selected strip
                    overlap_nexts.append(strip)
                if (strip.frame_final_end > selected_strip.frame_final_start) & (strip.frame_final_end < selected_strip.frame_final_end) & (strip.frame_final_start < selected_strip.frame_final_start):
                    #current strip endpoint is overlapping selected strip
                    overlap_previous.append(strip)

        nexts_all = nexts + overlap_nexts
        previous_all = previous + overlap_previous
        if direction == 'next':
            if mode == 'overlap':
                if len(overlap_nexts) > 0:
                    found = min(overlap_nexts, key=lambda overlap: abs(overlap.channel - selected_strip.channel))
            elif mode == 'channel' or mode == 'nooverlap':
                if len(nexts) > 0:
                    found = min(nexts, key=lambda next_seq: (next_seq.frame_final_start - selected_strip.frame_final_end))
            else:
                if len(nexts_all) > 0:
                    found = min(nexts_all, key=lambda next_seq: (next_seq.frame_final_start - selected_strip.frame_final_end))
        else:
            if mode == 'overlap':
                if len(overlap_previous) > 0:
                    found = min(overlap_previous, key=lambda overlap: abs(overlap.channel - selected_strip.channel))
            elif mode == 'channel' or mode == 'nooverlap':
                if len(previous) > 0:
                    found = min(previous, key=lambda prev: (selected_strip.frame_final_start - prev.frame_final_end))
            else:
                if len(previous_all) > 0:
                    found = min(previous_all, key=lambda prev: (selected_strip.frame_final_start - prev.frame_final_end))
    return found


def sequencer_used_height(left, right, strips=None):
    #determines the highest and lowest used channel in the sequencer in the given frame range.
    top = 0
    bottom = 0
    if not strips:
        strips = current_strips(bpy.context)
    for seq in strips:
        start = seq.frame_final_start
        end = seq.frame_final_end
        if (start > left and start < right) or (end > left and end < right) or (start < left and end > right):
            if bottom == 0:
                bottom = seq.channel
            elif seq.channel < bottom:
                bottom = seq.channel
            if seq.channel > top:
                top = seq.channel
    return [bottom, top]


def sequencer_area_clear(strips, left, right, bottom, top):
    del bottom
    del top
    #checks if strips ahead of the given area can fit in the given area
    width = right - left
    max_bottom, max_top = sequencer_used_height(right, right+1+width, strips=strips)
    if not sequencer_area_filled(left, right, max_bottom, max_top, [], strips=strips):
        return True
    return False


def sequencer_area_filled(left, right, bottom, top, omit, strips=False, quick=True):
    """Iterates through strips and checks if any are partially or fully in the given area
    Arguments:
        left: Starting frame of the area to check
        right: Ending frame of the area to check
        bottom: Lowest channel of the area to check
        top: Highest channel of the area to check, set to -1 for infinite range
        omit: List of strips to ignore
        strips: List of strips to check, if not given, bpy.context.scene.sequence_editor.strips will be used
        quick: If True, the function will stop iterating and return True on the first match, otherwise returns list of
            all matches

    Returns: If quick=True, returns True if a strip is in the area, False if none are in the area.
        If quick==False, returns a list of all matching strips if any are in the given area."""

    right = right
    if top != -1:
        if bottom > top:
            old_top = top
            top = bottom
            bottom = old_top
    matches = []
    if not strips:
        strips = current_strips(bpy.context)
    for strip in strips:
        if strip not in omit:
            if strip.channel >= bottom and (strip.channel <= top or top == -1):
                start = strip.frame_final_start
                end = strip.frame_final_end
                #strip start is inside area             strip end is inside area         entire strip is covering area
                if (start >= left and start < right) or (end > left and end <= right) or (start <= left and end >= right):
                    if quick:
                        return True
                    else:
                        matches.append(strip)
    if matches and not quick:
        return matches
    return False


def under_cursor(strip, frame):
    """Check if a strip is visible on a frame
    Arguments:
        strip: VSE strip object to check
        frame: Integer, the frame number

    Returns: True or False"""
    if strip.frame_final_start < frame and strip.frame_final_end > frame:
        return True
    else:
        return False


def in_muted_channel(sequence_editor, strip):
    """Check if a strip is in a muted channel
    Arguments:
        sequence_editor: current sequencer
        strip: VSE strip object to check

    Returns: True or False"""
    return sequence_editor.channels[strip.channel].mute


def in_locked_channel(sequence_editor, strip):
    """Check if a strip is in a locked channel
    Arguments:
        sequence_editor: current sequencer
        strip: VSE strip object to check

    Returns: True or False"""
    return sequence_editor.channels[strip.channel].lock


def is_muted(sequence_editor, strip):
    return strip.mute or in_muted_channel(sequence_editor, strip)


def is_locked(sequence_editor, strip):
    return strip.lock or in_locked_channel(sequence_editor, strip)


def get_vse_position(context):
    region = context.region
    view = region.view2d

    #determine the view area
    width = region.width
    height = region.height
    left, bottom = view.region_to_view(0, 0)
    right, top = view.region_to_view(width, height)
    return [left, right, bottom, top]


class VSEQFQuickTimeline(bpy.types.Operator):
    """Operator to adjust the VSE timeline in various ways

    Argument:
        operation: String, the operation to be performed.
            'strips': Trims the timeline to all strips in the VSE.  If no strips are loaded, timeline is not changed.
            'selected': Trims the timeline to the selected strip(s) in the VSE.  If no strips are selected, timeline is not changed.
            'strips_start': Like 'strips', but only trims the start frame.
            'strips_end': Like 'strips, but only trims the end frame.
            'selected_start': Like 'selected', but only trims the start frame.
            'selected_end': Like 'selected', but only trims the end frame.
            'full_auto': moves strips and markers back or up to match with frame 1, then sets start and end to encompass all sequences."""

    bl_idname = 'vseqf.quicktimeline'
    bl_label = 'VSEQF Quick Timeline'

    operation: bpy.props.StringProperty()
    tooltip: bpy.props.StringProperty("")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):
        operation = self.operation
        if 'selected' in operation:
            strips = current_selected(context)
        else:
            strips = current_strips(context)
        if strips:
            bpy.ops.ed.undo_push()
            if operation == 'full_auto':
                start_frame = find_strips_start(strips)
                end_frame = find_strips_end(strips)
                if start_frame != 1:
                    #move all strips forward then back
                    offset_1 = end_frame - start_frame + 1
                    offset_2 = -offset_1 - start_frame + 1

                    for marker in context.scene.timeline_markers:
                        marker.frame = int(marker.frame - start_frame + 1)

                    for strip in strips:
                        if not hasattr(strip, 'input_1'):
                            strip.frame_start = strip.frame_start + offset_1
                    for strip in strips:
                        if not hasattr(strip, 'input_1'):
                            strip.frame_start = strip.frame_start + offset_2
                    strips = current_strips(context)
            starts = []
            ends = []
            for strip in strips:
                starts.append(strip.frame_final_start)
                ends.append(strip.frame_final_end)
            starts.sort()
            ends.sort()
            newstart = starts[0]
            if newstart < 1:
                newstart = 1
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


class VSEQFQuickTimelineMenu(bpy.types.Menu):
    bl_idname = "VSEQF_MT_quicktimeline_menu"
    bl_label = "Timeline"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator('vseqf.check_clipping')
        layout.separator()
        props = layout.operator('vseqf.quicktimeline', text='Timeline To All')
        props.operation = 'strips'
        props.tooltip = 'Trims the timeline to all strips'
        props = layout.operator('vseqf.quicktimeline', text='Timeline To Selected')
        props.operation = 'selected'
        props.tooltip = 'Trims the timeline to selected strip(s)'
        layout.separator()
        props = layout.operator('vseqf.quicktimeline', text='Timeline Start To All')
        props.operation = 'strips_start'
        props.tooltip = 'Sets the timeline start to the start of the first strip'
        props = layout.operator('vseqf.quicktimeline', text='Timeline End To All')
        props.operation = 'strips_end'
        props.tooltip = 'Sets the timeline end to the end of the last strip'
        props = layout.operator('vseqf.quicktimeline', text='Timeline Start To Selected')
        props.operation = 'selected_start'
        props.tooltip = 'Sets the timeline start to the start of the first selected strip'
        props = layout.operator('vseqf.quicktimeline', text='Timeline End To Selected')
        props.operation = 'selected_end'
        props.tooltip = 'Sets the timeline end to the end of the last selected strip'
        row = layout.row()
        props = row.operator('vseqf.quicktimeline', text='Full Timeline Setup')
        props.operation = 'full_auto'
        props.tooltip = 'Moves strips and markers back up to frame 1, then sets start and end to encompass all strips'
        row.enabled = not inside_meta_strip()
