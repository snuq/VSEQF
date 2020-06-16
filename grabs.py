import bpy
import os
from . import vseqf
from . import timeline
from . import parenting
from . import fades
from . import vu_meter


marker_area_height = 40
marker_grab_distance = 100


class SequencePlaceHolder(object):
    sequence = None
    name = ''
    frame_final_start = 0
    frame_final_end = 0
    frame_final_duration = 0
    frame_start = 0
    channel = 0
    select = False
    select_left_handle = False
    select_right_handle = False
    rippled = False
    parent_data = None


def move_sequence_position(context, sequence, offset_x, offset_y, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end):
    #Move a sequence by a given offset

    new_start = start_frame_final_start + offset_x
    new_end = start_frame_final_end + offset_x
    channel = start_channel + offset_y
    if channel < 1:
        channel = 1
    while timeline.sequencer_area_filled(new_start, new_end, channel, channel, [sequence]):
        channel = channel + 1

    sequence.channel = channel
    sequence.frame_start = start_frame_start + offset_x


def move_sequence_left_handle(context, sequence, offset_x, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end, fix_fades=False, only_fix=False):
    #Move a sequence left handle and keep it behaving properly

    frame_final_end = start_frame_final_end
    frame_start_backup = sequence.frame_start
    sequence.channel = start_channel
    sequence.frame_start = frame_start_backup
    new_start = start_frame_final_start + offset_x
    if sequence.frame_duration == 1 and sequence.type in ['IMAGE', 'ADJUSTMENT', 'MULTICAM', 'TEXT', 'COLOR']:
        #Account for odd behavior of images and unbound effect strips
        if new_start >= sequence.frame_final_end:
            #Prevent left handle from being moved beyond ending point of strip
            new_start = sequence.frame_final_end - 1
        if sequence.frame_final_start != new_start:
            sequence.frame_start = new_start
        if sequence.frame_final_end != frame_final_end:
            sequence.frame_final_end = frame_final_end
    else:  #Normal strip
        if new_start >= frame_final_end - sequence.frame_still_end:
            #Prevent left handle from being moved beyond ending point of strip
            new_start = frame_final_end - 1 - sequence.frame_still_end
        if sequence.type == 'SOUND':
            #Prevent sound strip beginning from being dragged beyond start point
            if new_start < sequence.frame_start:
                new_start = sequence.frame_start
        new_position = start_frame_start
        if sequence.frame_final_start != new_start:
            sequence.frame_final_start = new_start
        if sequence.frame_start != new_position:
            sequence.frame_start = new_position
        if fix_fades:
            fades.fix_fade_in(context, sequence, start_frame_final_start)


def move_sequence_right_handle(context, sequence, offset_x, start_channel, start_frame_final_end, fix_fades=False, only_fix=False):
    #Move sequence right handle and keep it behaving properly

    frame_start_backup = sequence.frame_start
    sequence.channel = start_channel
    sequence.frame_start = frame_start_backup
    new_end = start_frame_final_end + offset_x
    if new_end <= sequence.frame_final_start + 1 + sequence.frame_still_start:
        #Prevent right handle from being moved beyond start point of strip
        new_end = sequence.frame_final_start + 1 + sequence.frame_still_start
    if sequence.type == 'SOUND':
        if new_end > sequence.frame_start + sequence.frame_duration:
            new_end = sequence.frame_start + sequence.frame_duration
    sequence.frame_final_end = new_end
    if fix_fades:
        fades.fix_fade_out(context, sequence, start_frame_final_end)


def move_sequence(context, sequence, offset_x, offset_y, select_left, select_right, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end, ripple=False, fix_fades=False, only_fix=False):
    if not select_left and not select_right and not only_fix:  #Move strip
        #check this first for efficiency since probably the most strips will be only middle-selected
        move_sequence_position(context, sequence, offset_x, offset_y, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end)
        return

    new_channel = start_channel + offset_y
    if select_left or select_right and not ripple:
        #make sequences that are having the handles adjusted behave better
        new_start = sequence.frame_final_start
        new_end = sequence.frame_final_end
        while timeline.sequencer_area_filled(new_start, new_end, new_channel, new_channel, [sequence]):
            new_channel = new_channel + 1
    if new_channel != sequence.channel:
        old_frame_start = sequence.frame_start
        sequence.channel = new_channel
        if sequence.frame_start != old_frame_start:
            #For some reason, the first time a grab is run, the channel setting doesnt work right... double check and fix if needed
            sequence.frame_start = old_frame_start

    if select_left:  #Move left handle
        move_sequence_left_handle(context, sequence, offset_x, new_channel, start_frame_start, start_frame_final_start, start_frame_final_end, fix_fades=fix_fades, only_fix=only_fix)
    if select_right:  #Move right handle
        move_sequence_right_handle(context, sequence, offset_x, new_channel, start_frame_final_end, fix_fades=fix_fades, only_fix=only_fix)


def find_data_by_name(name, sequences):
    #finds the sequence data matching the given name.
    for seq in sequences:
        if seq.sequence.name == name:
            return seq
    return False


def copy_sequence(sequence):
    data = SequencePlaceHolder()
    data.sequence = sequence
    data.name = sequence.name
    data.frame_final_start = sequence.frame_final_start
    data.frame_final_end = sequence.frame_final_end
    data.frame_final_duration = sequence.frame_final_duration
    data.frame_start = sequence.frame_start
    data.channel = sequence.channel
    data.select = sequence.select
    data.select_left_handle = sequence.select_left_handle
    data.select_right_handle = sequence.select_right_handle
    return data


def copy_sequences(sequences):
    sequences_data = []
    for sequence in sequences:
        sequences_data.append(copy_sequence(sequence))
    return sequences_data


def grab_starting_data(sequences):
    data = {}
    for sequence in sequences:
        data[sequence.name] = copy_sequence(sequence)
    return data


def move_sequences(context, starting_data, offset_x, offset_y, grabbed_sequences, fix_fades=False, ripple=False, ripple_pop=False, move_root=True, child_edges=False):
    ripple_offset = 0
    right_edges = []

    #Adjust grabbed strips
    for sequence in grabbed_sequences:
        data = starting_data[sequence.name]
        move_sequence(context, sequence, offset_x, offset_y, data.select_left_handle, data.select_right_handle, data.channel, data.frame_start, data.frame_final_start, data.frame_final_end, ripple=ripple, fix_fades=fix_fades, only_fix=not move_root)
        right_edges.append(sequence.frame_final_end)

        if ripple:
            if sequence.select_left_handle and not sequence.select_right_handle and len(grabbed_sequences) == 1:
                #special ripple slide if only one sequence and left handle grabbed
                frame_start = data.frame_final_start
                ripple_offset = ripple_offset + frame_start - sequence.frame_final_start
                sequence.frame_start = data.frame_start + ripple_offset
                #offset_x = ripple_offset
            else:
                if ripple_pop and sequence.channel != data.channel:
                    #ripple 'pop'
                    ripple_offset = sequence.frame_final_duration
                    ripple_offset = 0 - ripple_offset
                else:
                    ripple_offset = data.frame_final_end - sequence.frame_final_end
                    ripple_offset = 0 - ripple_offset

        if vseqf.parenting():
            #Adjust children of grabbed sequence
            children = parenting.get_recursive(sequence, [])
            root_offset_x = sequence.frame_start - data.frame_start
            root_offset_y = sequence.channel - data.channel
            for child in children:
                if child == sequence:
                    continue
                child_data = starting_data[child.name]
                if child.parent == sequence.name:
                    #Primary children
                    if data.select_left_handle or data.select_right_handle:
                        #Move edges along with parent if applicable
                        if context.scene.vseqf.move_edges:
                            if child_data.frame_final_start == data.frame_final_start:
                                select_left = data.select_left_handle
                            else:
                                select_left = False
                            if child_data.frame_final_end == data.frame_final_end:
                                select_right = data.select_right_handle
                            else:
                                select_right = False
                            if select_left or select_right:
                                move_sequence(context, child, offset_x, offset_y, select_left, select_right, child_data.channel, child_data.frame_start, child_data.frame_final_start, child_data.frame_final_end, ripple=ripple, fix_fades=fix_fades)
                        if not data.select_right_handle:
                            child.frame_start = child_data.frame_start + ripple_offset
                    else:
                        move_sequence(context, child, root_offset_x, root_offset_y, False, False, child_data.channel, child_data.frame_start, child_data.frame_final_start, child_data.frame_final_end)
                else:
                    #Children of children, only move them if the root sequence has moved
                    move_sequence(context, child, root_offset_x, root_offset_y, False, False, child_data.channel, child_data.frame_start, child_data.frame_final_start, child_data.frame_final_end)
                if child_edges:
                    #Snap edges of children to edge of parent
                    if sequence.select_left_handle:
                        child.frame_final_start = sequence.frame_final_start
                    if sequence.select_right_handle:
                        child.frame_final_end = sequence.frame_final_end

    return ripple_offset


def grab_ripple_sequences(starting_data, ripple_sequences, ripple, ripple_offset):
    for sequence in ripple_sequences:
        data = starting_data[sequence.name]
        if ripple:
            data.rippled = True
            new_channel = data.channel
            while timeline.sequencer_area_filled(data.frame_final_start + ripple_offset, data.frame_final_end + ripple_offset, new_channel, new_channel, [sequence]):
                new_channel = new_channel + 1
            sequence.channel = new_channel
            sequence.frame_start = data.frame_start + ripple_offset

        if data.rippled and not ripple:
            #fix sequence locations when ripple is disabled
            new_channel = data.channel
            new_start = data.frame_final_start
            new_end = data.frame_final_end
            while timeline.sequencer_area_filled(new_start, new_end, new_channel, new_channel, [sequence]):
                new_channel = new_channel + 1
            sequence.channel = new_channel
            sequence.frame_start = data.frame_start
            if sequence.frame_start == data.frame_start and sequence.channel == data.channel:
                #unfortunately, there seems to be a limitation in blender preventing me from putting the strip back where it should be... keep trying until the grabbed strips are out of the way.
                data.rippled = False


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


class VSEQFSelectGrab(bpy.types.Operator):
    """Replacement for the right and left-click select operator and context menu"""
    bl_idname = "vseqf.select_grab"
    bl_label = "Grab/Move Sequence"

    mouse_start_x = 0
    mouse_start_y = 0
    mouse_start_region_x = 0
    mouse_start_region_y = 0
    selected = []
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
                location = view.region_to_view(self.mouse_start_region_x, self.mouse_start_region_y)
                click_frame, click_channel = location
                is_near_marker = near_marker(context, click_frame)
                if event.mouse_region_y <= marker_area_height:
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
        selected_sequences = timeline.current_selected(context)
        for sequence in selected_sequences:
            self.selected.append([sequence, sequence.select_left_handle, sequence.select_right_handle])
        if event.mouse_region_y > marker_area_height:
            bpy.ops.sequencer.select('INVOKE_DEFAULT', deselect_all=True)
        selected_sequences = timeline.current_selected(context)
        if not selected_sequences:
            return {'FINISHED'}
        prefs = vseqf.get_prefs()
        if prefs.threepoint:
            active = timeline.current_active(context)
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
                to_select = parenting.get_recursive(sequence, to_select)
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


class VSEQFGrabAdd(bpy.types.Operator):
    """Modal operator designed to run in tandem with the built-in grab operator."""
    bl_idname = "vseqf.grabadd"
    bl_label = "Runs in tandem with the grab operator in the vse, adds functionality."

    mode: bpy.props.StringProperty()
    snap_cursor_to_edge = False
    grabbed_sequences = []
    ripple_sequences = []
    target_grab_sequence = None
    target_grab_variable = ''
    target_grab_start = 0
    target_grab_channel = 1
    sequences = []
    starting_data = {}
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
            sequence = seq
            window_x, window_y = view.view_to_region(sequence.frame_final_start, sequence.channel)
            vseqf.draw_text(window_x, window_y - 6, 12, mode, text_color)

    def reset_sequences(self):
        #used when cancelling, puts everything back to where it was at the beginning by first moving it somewhere safe, then to the true location

        timeline_length = self.timeline_end - self.timeline_start

        for sequence in self.sequences:
            data = self.starting_data[sequence.name]
            if not hasattr(sequence, 'input_1'):
                sequence.channel = data.channel + self.timeline_height
                sequence.frame_start = data.frame_start + timeline_length
                sequence.frame_final_start = data.frame_final_start + timeline_length
                sequence.frame_final_end = data.frame_final_end + timeline_length
            else:
                sequence.channel = data.channel + self.timeline_height
        for sequence in self.sequences:
            data = self.starting_data[sequence.name]
            if not hasattr(sequence, 'input_1'):
                sequence.channel = data.channel
                sequence.frame_start = data.frame_start
            else:
                sequence.channel = data.channel
        return

    def modal(self, context, event):
        release_confirm = bpy.context.preferences.inputs.use_drag_immediately

        reset_sequences = False
        if event.type == 'TIMER':
            pass
        if event.type == 'E':
            #doesnt seem to work unfortunately... events other than timer are not being passed
            if not context.screen.is_animation_playing:
                if self.snap_cursor_to_edge:
                    self.snap_cursor_to_edge = False
                    context.scene.frame_current = self.start_frame
                    context.scene.sequence_editor.overlay_frame = self.start_overlay_frame
                else:
                    self.snap_cursor_to_edge = True
        if self.mode != 'SLIP':
            #prevent ripple and edge snap while in slip mode
            if event.alt:
                self.alt_pressed = True
            else:
                if self.alt_pressed:
                    reset_sequences = True
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

            if self.snap_cursor_to_edge:
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
        elif self.target_grab_variable == 'frame_final_end':
            pos_x = self.target_grab_sequence.frame_final_end
            offset_x = pos_x - self.target_grab_start
        elif self.target_grab_variable == 'frame_final_start':
            pos_x = self.target_grab_sequence.frame_final_start
            offset_x = pos_x - self.target_grab_start

        if self.target_grab_sequence.select_left_handle or self.target_grab_sequence.select_right_handle:
            offset_y = 0
        else:
            offset_y = pos_y - self.target_grab_channel

        if reset_sequences:
            self.reset_sequences()
        ripple_offset = move_sequences(context, self.starting_data, offset_x, offset_y, self.grabbed_sequences, ripple_pop=self.ripple_pop, fix_fades=False, ripple=self.ripple, move_root=False)
        grab_ripple_sequences(self.starting_data, self.ripple_sequences, self.ripple, ripple_offset)

        if event.type in {'LEFTMOUSE', 'RET'} or (release_confirm and event.value == 'RELEASE'):
            vu_meter.vu_meter_calculate(context.scene)
            self.remove_draw_handler()
            vseqf.redraw_sequencers()
            if self.prefs.fades:
                fix_fades = True
            else:
                fix_fades = False
            ripple_offset = move_sequences(context, self.starting_data, offset_x, offset_y, self.grabbed_sequences, ripple_pop=self.ripple_pop, fix_fades=fix_fades, ripple=self.ripple, move_root=False)
            grab_ripple_sequences(self.starting_data, self.ripple_sequences, self.ripple, ripple_offset)

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

    def invoke(self, context, event):
        self.start_frame = context.scene.frame_current
        self.start_overlay_frame = context.scene.sequence_editor.overlay_frame
        bpy.ops.ed.undo_push()
        self.cancelled = False
        self.prefs = vseqf.get_prefs()
        region = context.region
        self.view2d = region.view2d
        self.pos_x, self.pos_y = self.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        self.pos_x_start = self.pos_x
        self.pos_y_start = self.pos_y
        self.sequences = []
        self.grabbed_sequences = []
        self.ripple_sequences = []
        sequences = timeline.current_sequences(context)
        self.timeline_start = timeline.find_sequences_start(sequences)
        self.timeline_end = timeline.find_sequences_end(sequences)
        self.ripple_start = self.timeline_end
        self.timeline_height = timeline.find_timeline_height(sequences)
        is_parenting = vseqf.parenting()
        to_move = []
        selected_sequences = timeline.current_selected(context)
        for sequence in selected_sequences:
            if sequence.select_right_handle:
                ripple_point = sequence.frame_final_end
            else:
                ripple_point = sequence.frame_final_start
            if ripple_point < self.ripple_start and not hasattr(sequence, 'input_1') and not sequence.lock:
                self.ripple_start = ripple_point
                self.ripple_left = ripple_point
            if is_parenting:
                to_move = parenting.get_recursive(sequence, to_move)
            else:
                to_move.append(sequence)

        self.starting_data = grab_starting_data(sequences)
        #generate grabbed sequences and ripple sequences lists
        for sequence in sequences:
            if not sequence.lock and not hasattr(sequence, 'input_1'):
                self.sequences.append(sequence)
                if sequence.select:
                    self.grabbed_sequences.append(sequence)
                else:
                    if is_parenting and sequence in to_move:
                        pass
                    elif sequence.frame_final_start >= self.ripple_start:
                        self.ripple_sequences.append(sequence)
        self._timer = context.window_manager.event_timer_add(time_step=0.01, window=context.window)
        self.ripple_sequences.sort(key=lambda x: x.frame_final_start)
        self.grabbed_sequences.sort(key=lambda x: x.frame_final_start)
        grabbed_left = False
        grabbed_right = False
        grabbed_center = False
        for sequence in self.grabbed_sequences:
            if sequence.select and not (sequence.select_left_handle or sequence.select_right_handle):
                grabbed_center = sequence
            else:
                if sequence.select_left_handle:
                    grabbed_left = sequence
                if sequence.select_right_handle:
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
        if not context.screen.is_animation_playing:
            self.snap_cursor_to_edge = context.scene.vseqf.snap_cursor_to_edge
        else:
            self.snap_cursor_to_edge = False
        self.snap_edge = None
        self.snap_edge_sequence = None
        self.secondary_snap_edge = None
        self.secondary_snap_edge_sequence = None
        #Determine number of selected edges in grabbed sequences:
        selected_edges = []
        for sequence in self.grabbed_sequences:
            if sequence.select_left_handle:
                selected_edges.append([sequence, 'left'])
            if sequence.select_right_handle:
                selected_edges.append([sequence, 'right'])
        if len(selected_edges) == 1:
            #only one edge is grabbed, snap to it
            self.snap_edge_sequence = selected_edges[0][0]
            self.snap_edge = selected_edges[0][1]
        elif len(selected_edges) == 2:
            #two sequence edges are selected
            #if one sequence is active, make that primary
            active = timeline.current_active(context)
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
        if len(self.grabbed_sequences) == 1 and not (self.grabbed_sequences[0].select_left_handle or self.grabbed_sequences[0].select_right_handle):
            self.can_pop = True
        else:
            self.can_pop = False
        #bpy.ops.ed.undo_push()
        context.window_manager.modal_handler_add(self)
        args = (context, )
        self._handle = bpy.types.SpaceSequenceEditor.draw_handler_add(self.vseqf_grab_draw, args, 'WINDOW', 'POST_PIXEL')
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
        active = timeline.current_active(context)

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
        elif event.mouse_region_y <= marker_area_height:
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
        if timeline.inside_meta_strip():
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
        if timeline.inside_meta_strip():
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
        sequence = timeline.current_active(context)
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
        if timeline.inside_meta_strip():
            layout.operator('vseqf.meta_exit')
            layout.separator()
        layout.menu('SEQUENCER_MT_add')
        layout.menu('VSEQF_MT_quickzooms_menu')
        layout.menu('VSEQF_MT_quicktimeline_menu')


class VSEQFContextSequenceLeft(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_sequence_left"
    bl_label = "Operations On Left Handle"

    def draw(self, context):
        strip = timeline.current_active(context)
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        if timeline.inside_meta_strip():
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
        strip = timeline.current_active(context)
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        if timeline.inside_meta_strip():
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
        prefs = vseqf.get_prefs()
        strip = timeline.current_active(context)
        selected = timeline.current_selected(context)
        layout = self.layout
        layout.operator('vseqf.double_undo', text='Undo')
        if timeline.inside_meta_strip():
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
            if strip.type == 'SOUND':
                layout.operator_context = "INVOKE_DEFAULT"
                layout.operator('vseqf.volume_draw', text='Draw Volume Curve')
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
