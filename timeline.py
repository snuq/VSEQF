import bpy
from . import vseqf
from . import parenting


#Effect manipulation and cleanup
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


#Meta strip manipulations
def inside_meta_strip():
    try:
        if len(bpy.context.scene.sequence_editor.meta_stack) > 0:
            return True
    except:
        pass
    return False


class VSEQFMeta(bpy.types.Operator):
    """Creates meta strip while adding children"""

    bl_idname = 'vseqf.meta_make'
    bl_label = 'Make Meta Strip (Include Children)'

    def execute(self, context):
        bpy.ops.ed.undo_push()
        is_parenting = vseqf.parenting()
        if is_parenting:
            selected = current_selected(context)
            for sequence in selected:
                children = parenting.find_children(sequence)
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
                if add_parented or (not parenting.find_parent(seq)):
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
                if add_parented or (not parenting.find_parent(seq)):
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
                    if parenting.find_parent(current_sequence):
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
                    if parenting.find_parent(current_sequence):
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


def sequencer_used_height(left, right, sequences=None):
    #determines the highest and lowest used channel in the sequencer in the given frame range.
    top = 0
    bottom = 0
    if not sequences:
        sequences = current_sequences(bpy.context)
    for seq in sequences:
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


def sequencer_area_clear(sequences, left, right, bottom, top):
    del bottom
    del top
    #checks if strips ahead of the given area can fit in the given area
    width = right - left
    max_bottom, max_top = sequencer_used_height(right, right+1+width, sequences=sequences)
    if not sequencer_area_filled(left, right, max_bottom, max_top, [], sequences=sequences):
        return True
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

    right = right
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
                #strip start is inside area             strip end is inside area         entire strip is covering area
                if (start >= left and start < right) or (end > left and end <= right) or (start <= left and end >= right):
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


def in_muted_channel(sequence_editor, sequence):
    """Check if a sequence is in a muted channel
    Arguments:
        sequence_editor: current sequencer
        sequence: VSE sequence object to check

    Returns: True or False"""
    return sequence_editor.channels[sequence.channel].mute


def in_locked_channel(sequence_editor, sequence):
    """Check if a sequence is in a locked channel
    Arguments:
        sequence_editor: current sequencer
        sequence: VSE sequence object to check

    Returns: True or False"""
    return sequence_editor.channels[sequence.channel].lock


def is_muted(sequence_editor, sequence):
    return sequence.mute or in_muted_channel(sequence_editor, sequence)


def is_locked(sequence_editor, sequence):
    return sequence.lock or in_locked_channel(sequence_editor, sequence)


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
    tooltip: bpy.props.StringProperty("")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

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
        props.operation = 'sequences'
        props.tooltip = 'Trims the timeline to all sequences'
        props = layout.operator('vseqf.quicktimeline', text='Timeline To Selected')
        props.operation = 'selected'
        props.tooltip = 'Trims the timeline to selected sequence(s)'
        layout.separator()
        props = layout.operator('vseqf.quicktimeline', text='Timeline Start To All')
        props.operation = 'sequences_start'
        props.tooltip = 'Sets the timeline start to the start of the first sequence'
        props = layout.operator('vseqf.quicktimeline', text='Timeline End To All')
        props.operation = 'sequences_end'
        props.tooltip = 'Sets the timeline end to the end of the last sequence'
        props = layout.operator('vseqf.quicktimeline', text='Timeline Start To Selected')
        props.operation = 'selected_start'
        props.tooltip = 'Sets the timeline start to the start of the first selected sequence'
        props = layout.operator('vseqf.quicktimeline', text='Timeline End To Selected')
        props.operation = 'selected_end'
        props.tooltip = 'Sets the timeline end to the end of the last selected sequence'
        row = layout.row()
        props = row.operator('vseqf.quicktimeline', text='Full Timeline Setup')
        props.operation = 'full_auto'
        props.tooltip = 'Moves sequences back up to frame 1, then sets start and end to encompass all sequences'
        row.enabled = not inside_meta_strip()
