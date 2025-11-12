import bpy
import os
from . import vseqf
from . import timeline
from . import fades
from . import vu_meter


marker_area_height = 40
marker_grab_distance = 100


class StripPlaceHolder(object):
    strip = None
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


def get_click_mode(context):
    #Had to implement this because blender does not HAVE this setting when using a custom keymap. argh.
    try:
        click_mode = context.window_manager.keyconfigs.active.preferences.select_mouse
    except:
        click_mode = 'LEFT'
    return click_mode


def move_strip_position(context, strip, offset_x, offset_y, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end):
    #Move a strip by a given offset

    new_start = start_frame_final_start + offset_x
    new_end = start_frame_final_end + offset_x
    channel = start_channel + offset_y
    if channel < 1:
        channel = 1
    while timeline.sequencer_area_filled(new_start, new_end, channel, channel, [strip]):
        channel = channel + 1

    strip.channel = channel
    strip.frame_start = start_frame_start + offset_x


def move_strip_left_handle(context, strip, offset_x, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end, fix_fades=False, only_fix=False):
    #Move a strip left handle and keep it behaving properly

    frame_final_end = start_frame_final_end
    frame_start_backup = strip.frame_start
    strip.channel = start_channel
    strip.frame_start = frame_start_backup
    new_start = start_frame_final_start + offset_x
    if strip.frame_duration == 1 and strip.type in ['IMAGE', 'ADJUSTMENT', 'MULTICAM', 'TEXT', 'COLOR']:
        #Account for odd behavior of images and unbound effect strips
        if new_start >= strip.frame_final_end:
            #Prevent left handle from being moved beyond ending point of strip
            new_start = strip.frame_final_end - 1
        if strip.frame_final_start != new_start:
            strip.frame_start = new_start
        if strip.frame_final_end != frame_final_end:
            strip.frame_final_end = int(frame_final_end)
    else:  #Normal strip
        if new_start >= frame_final_end + strip.frame_offset_end:
            #Prevent left handle from being moved beyond ending point of strip
            new_start = frame_final_end - 1 + strip.frame_offset_end
        #if strip.type == 'SOUND':
        #    #Prevent sound strip beginning from being dragged beyond start point
        #    if new_start < strip.frame_start:
        #        new_start = strip.frame_start
        new_position = start_frame_start
        if strip.frame_final_start != new_start:
            strip.frame_final_start = int(new_start)
        if strip.frame_start != new_position:
            strip.frame_start = int(new_position)
        if fix_fades:
            fades.fix_fade_in(context, strip, start_frame_final_start)


def move_strip_right_handle(context, strip, offset_x, start_channel, start_frame_final_end, fix_fades=False, only_fix=False):
    #Move strip right handle and keep it behaving properly

    frame_start_backup = strip.frame_start
    strip.channel = start_channel
    strip.frame_start = frame_start_backup
    new_end = start_frame_final_end + offset_x
    if new_end <= strip.frame_final_start + 1 - strip.frame_offset_start:
        #Prevent right handle from being moved beyond start point of strip
        new_end = strip.frame_final_start + 1 - strip.frame_offset_start
    #if strip.type == 'SOUND':
    #    if new_end > strip.frame_start + strip.frame_duration:
    #        new_end = strip.frame_start + strip.frame_duration
    strip.frame_final_end = int(new_end)
    if fix_fades:
        fades.fix_fade_out(context, strip, start_frame_final_end)


def move_strip(context, strip, offset_x, offset_y, select_left, select_right, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end, ripple=False, fix_fades=False, only_fix=False):
    if not select_left and not select_right and not only_fix:  #Move strip
        #check this first for efficiency since probably the most strips will be only middle-selected
        move_strip_position(context, strip, offset_x, offset_y, start_channel, start_frame_start, start_frame_final_start, start_frame_final_end)
        return

    new_channel = start_channel + offset_y
    if select_left or select_right and not ripple:
        #make strips that are having the handles adjusted behave better
        new_start = strip.frame_final_start
        new_end = strip.frame_final_end
        while timeline.sequencer_area_filled(new_start, new_end, new_channel, new_channel, [strip]):
            new_channel = new_channel + 1
    if new_channel != strip.channel:
        old_frame_start = strip.frame_start
        strip.channel = new_channel
        if strip.frame_start != old_frame_start:
            #For some reason, the first time a grab is run, the channel setting doesn't work right... double check and fix if needed
            strip.frame_start = old_frame_start

    if select_left:  #Move left handle
        move_strip_left_handle(context, strip, offset_x, new_channel, start_frame_start, start_frame_final_start, start_frame_final_end, fix_fades=fix_fades, only_fix=only_fix)
    if select_right:  #Move right handle
        move_strip_right_handle(context, strip, offset_x, new_channel, start_frame_final_end, fix_fades=fix_fades, only_fix=only_fix)


def copy_strip(strip):
    data = StripPlaceHolder()
    data.strip = strip
    data.name = strip.name
    data.frame_final_start = strip.frame_final_start
    data.frame_final_end = strip.frame_final_end
    data.frame_final_duration = strip.frame_final_duration
    data.frame_start = strip.frame_start
    data.channel = strip.channel
    data.select = strip.select
    data.select_left_handle = strip.select_left_handle
    data.select_right_handle = strip.select_right_handle
    return data


def grab_starting_data(strips):
    data = {}
    for strip in strips:
        data[strip.name] = copy_strip(strip)
    return data


def move_strips(context, starting_data, offset_x, offset_y, grabbed_strips, fix_fades=False, ripple=False, ripple_pop=False, move_root=True, child_edges=False):
    ripple_offset = 0
    right_edges = []

    #Adjust grabbed strips
    for strip in grabbed_strips:
        data = starting_data[strip.name]
        move_strip(context, strip, offset_x, offset_y, data.select_left_handle, data.select_right_handle, data.channel, data.frame_start, data.frame_final_start, data.frame_final_end, ripple=ripple, fix_fades=fix_fades, only_fix=not move_root)
        right_edges.append(strip.frame_final_end)

        if ripple:
            if strip.select_left_handle and not strip.select_right_handle and len(grabbed_strips) == 1:
                #special ripple slide if only one strip and left handle grabbed
                frame_start = data.frame_final_start
                ripple_offset = ripple_offset + frame_start - strip.frame_final_start
                strip.frame_start = data.frame_start + ripple_offset
                #offset_x = ripple_offset
            else:
                if ripple_pop and strip.channel != data.channel:
                    #ripple 'pop'
                    ripple_offset = strip.frame_final_duration
                    ripple_offset = 0 - ripple_offset
                else:
                    ripple_offset = data.frame_final_end - strip.frame_final_end
                    ripple_offset = 0 - ripple_offset

    return ripple_offset


def grab_ripple_markers(ripple_markers, ripple, ripple_offset):
    for marker_data in ripple_markers:
        marker, original_frame = marker_data
        if ripple:
            marker.frame = original_frame + ripple_offset
        else:
            marker.frame = original_frame


def grab_ripple_strips(starting_data, ripple_strips, ripple, ripple_offset):
    for strip in ripple_strips:
        data = starting_data[strip.name]
        if ripple:
            data.rippled = True
            new_channel = data.channel
            while timeline.sequencer_area_filled(data.frame_final_start + ripple_offset, data.frame_final_end + ripple_offset, new_channel, new_channel, [strip]):
                new_channel = new_channel + 1
            strip.channel = new_channel
            strip.frame_start = data.frame_start + ripple_offset

        if data.rippled and not ripple:
            #fix strip locations when ripple is disabled
            new_channel = data.channel
            new_start = data.frame_final_start
            new_end = data.frame_final_end
            while timeline.sequencer_area_filled(new_start, new_end, new_channel, new_channel, [strip]):
                new_channel = new_channel + 1
            strip.channel = new_channel
            strip.frame_start = data.frame_start
            if strip.frame_start == data.frame_start and strip.channel == data.channel:
                #unfortunately, there seems to be a limitation in blender preventing me from putting the strip back where it should be... keep trying until the grabbed strips are out of the way.
                data.rippled = False


def ripple_timeline(sequencer, strips, start_frame, ripple_amount, select_ripple=True, markers=[]):
    """Moves all given strips starting after the frame given as 'start_frame', by moving them forward by 'ripple_amount' frames.
    'select_ripple' will select all strips that were moved."""

    to_change = []
    for strip in strips:
        if not timeline.is_locked(sequencer, strip) and strip.frame_final_end > start_frame - ripple_amount and strip.frame_final_start > start_frame:
            to_change.append([strip, strip.channel, strip.frame_start + ripple_amount, True])
    for seq in to_change:
        strip = seq[0]
        strip.channel = seq[1]
        if not hasattr(strip, 'input_1'):
            strip.frame_start = seq[2]
        if select_ripple:
            strip.select = True
        if (strip.frame_start != seq[2] or strip.channel != seq[1]) and seq[3]:
            seq[3] = False
            to_change.append(seq)
    if markers:
        for marker in markers:
            if marker.frame >= (start_frame - ripple_amount):
                marker.frame = marker.frame + ripple_amount


def near_marker(context, frame, distance=None):
    if distance is None:
        distance = marker_grab_distance
    if context.scene.timeline_markers:
        markers = sorted(context.scene.timeline_markers, key=lambda x: abs(x.frame - frame))
        marker = markers[0]
        if abs(marker.frame - frame) <= distance:
            return marker
    return None


def on_strip(frame, channel, strip):
    if frame >= strip.frame_final_start and frame <= strip.frame_final_end and int(channel) == strip.channel:
        return True
    else:
        return False


class VSEQFSelectGrabTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_context_mode = 'SEQUENCER'  #Also could be PREVIEW or SEQUENCER_PREVIEW

    bl_idname = "vseqf.select_grab_tool"
    bl_label = "Move Plus"
    bl_description = (
        "Select and move a strip, with extra features."
    )
    bl_icon = "ops.generic.select"
    bl_widget = None
    bl_keymap = (
        ("vseqf.select_grab", {"type": 'RIGHTMOUSE', "value": 'PRESS'}, None),
        ("vseqf.select_grab", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("vseqf.select_grab", {"type": 'RIGHTMOUSE', "value": 'PRESS', "ctrl": True}, None),
        ("vseqf.select_grab", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True}, None),
        ("vseqf.select_grab", {"type": 'RIGHTMOUSE', "value": 'PRESS', "alt": True}, None),
        ("vseqf.select_grab", {"type": 'LEFTMOUSE', "value": 'PRESS', "alt": True}, None),
        ("vseqf.select_grab", {"type": 'RIGHTMOUSE', "value": 'PRESS', "ctrl": True, "alt": True}, None),
        ("vseqf.select_grab", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True, "alt": True}, None),
    )

    def draw_settings(self, layout, tool):
        props = tool.operator_properties("vseqf.select_grab")
        layout.prop(props, "mode")


class VSEQFSelectGrab(bpy.types.Operator):
    """Replacement for the right and left-click select operator and context menu"""
    bl_idname = "vseqf.select_grab"
    bl_label = "Grab/Move Strip"

    mouse_start_x = 0
    mouse_start_y = 0
    mouse_start_region_x = 0
    mouse_start_region_y = 0
    selected = []
    _timer = None
    click_mode = None

    @classmethod
    def poll(cls, context):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            return False
        return not sequencer.selected_retiming_keys

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
        bpy.ops.ed.undo_push()
        prefs = vseqf.get_prefs()
        self.click_mode = get_click_mode(context)
        if self.click_mode == 'RIGHT' and event.type == 'LEFTMOUSE':
            #in RCS, left click on squencer, move cursor if nothing is clickd on
            region = context.region
            view = region.view2d
            location = view.region_to_view(event.mouse_region_x, event.mouse_region_y)
            click_frame, click_channel = location
            clicked_strip = None
            for strip in context.scene.sequence_editor.strips:
                if on_strip(click_frame, click_channel, strip):
                    clicked_strip = strip
                    break
            if not clicked_strip:
                bpy.ops.anim.change_frame('INVOKE_DEFAULT')
                return {'FINISHED'}
        if event.type == 'RIGHTMOUSE':
            #right click, maybe do context menus
            if prefs.context_menu:
                bpy.ops.vseqf.context_menu('INVOKE_DEFAULT')
            else:
                bpy.ops.wm.call_menu(name="SEQUENCER_MT_context_menu")
            if self.click_mode == 'LEFT':
                return {'FINISHED'}
        self.selected = []
        original_selected_strips = timeline.current_selected(context)
        for strip in original_selected_strips:
            self.selected.append([strip, strip.select_left_handle, strip.select_right_handle])
        #if event.mouse_region_y > marker_area_height:
        if event.ctrl and event.alt:
            return {'FINISHED'}
        elif event.ctrl:
            bpy.ops.sequencer.select('INVOKE_DEFAULT', deselect_all=False, linked_time=True)
            return {'FINISHED'}
        elif event.alt:
            bpy.ops.sequencer.select('INVOKE_DEFAULT', deselect_all=True, linked_handle=True)
        else:
            bpy.ops.sequencer.select('INVOKE_DEFAULT', deselect_all=True)
        selected_strips = timeline.current_selected(context)
        if not selected_strips:
            bpy.ops.sequencer.select_box('INVOKE_DEFAULT')
            return {'FINISHED'}
        prefs = vseqf.get_prefs()
        if prefs.threepoint:
            active = timeline.current_active(context)
            if active and active.type == 'MOVIE':
                #look for a clip editor area and set the active clip to the selected strip if one exists that shares the same source.
                newclip = None
                for clip in bpy.data.movieclips:
                    if os.path.normpath(bpy.path.abspath(clip.filepath)) == os.path.normpath(bpy.path.abspath(active.filepath)):
                        newclip = clip
                        break
                if newclip:
                    for area in context.screen.areas:
                        if area.type == 'CLIP_EDITOR':
                            area.spaces[0].clip = newclip

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
    grabbed_strips = []
    ripple_strips = []
    target_grab_strip = None
    target_grab_variable = ''
    target_grab_start = 0
    target_grab_channel = 1
    strips = []
    starting_data = {}
    ripple_markers = []
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
    snap_edge_strip = None
    secondary_snap_edge = None
    secondary_snap_edge_strip = None
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
        for strip in self.grabbed_strips:
            window_x, window_y = view.view_to_region(strip.frame_final_start, strip.channel)
            vseqf.draw_text(window_x, window_y - 6, 12, mode, text_color)

    def reset_markers(self):
        for marker_data in self.ripple_markers:
            marker, original_frame = marker_data
            marker.frame = original_frame

    def reset_strips(self):
        #used when cancelling, puts everything back to where it was at the beginning by first moving it somewhere safe, then to the true location

        self.reset_markers()
        timeline_length = self.timeline_end - self.timeline_start

        for strip in self.strips:
            data = self.starting_data[strip.name]
            if not hasattr(strip, 'input_1'):
                strip.channel = data.channel + self.timeline_height
                strip.frame_start = data.frame_start + timeline_length
                strip.frame_final_start = data.frame_final_start + timeline_length
                strip.frame_final_end = data.frame_final_end + timeline_length
            else:
                strip.channel = data.channel + self.timeline_height
        for strip in self.strips:
            data = self.starting_data[strip.name]
            if not hasattr(strip, 'input_1'):
                strip.channel = data.channel
                strip.frame_start = data.frame_start
            else:
                strip.channel = data.channel

    def modal(self, context, event):
        release_confirm = bpy.context.preferences.inputs.use_drag_immediately

        reset_strips = False
        if event.type == 'TIMER':
            pass
        if event.type == 'E':
            #doesn't seem to work unfortunately... events other than timer are not being passed
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
                    reset_strips = True
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
                        frame = self.snap_edge_strip.frame_final_start
                    else:
                        frame = self.snap_edge_strip.frame_final_end - 1
                    context.scene.frame_current = frame
                    if self.secondary_snap_edge:
                        if self.secondary_snap_edge == 'left':
                            overlay_frame = self.secondary_snap_edge_strip.frame_final_start
                        else:
                            overlay_frame = self.secondary_snap_edge_strip.frame_final_end - 1
                        context.scene.sequence_editor.overlay_frame = overlay_frame - frame
        offset_x = 0
        pos_y = self.target_grab_strip.channel
        if self.target_grab_variable == 'frame_start':
            pos_x = self.target_grab_strip.frame_start
            offset_x = pos_x - self.target_grab_start
        elif self.target_grab_variable == 'frame_final_end':
            pos_x = self.target_grab_strip.frame_final_end
            offset_x = pos_x - self.target_grab_start
        elif self.target_grab_variable == 'frame_final_start':
            pos_x = self.target_grab_strip.frame_final_start
            offset_x = pos_x - self.target_grab_start

        if self.target_grab_strip.select_left_handle or self.target_grab_strip.select_right_handle:
            offset_y = 0
        else:
            offset_y = pos_y - self.target_grab_channel

        if reset_strips:
            self.reset_strips()
        ripple_offset = move_strips(context, self.starting_data, offset_x, offset_y, self.grabbed_strips, ripple_pop=self.ripple_pop, fix_fades=False, ripple=self.ripple, move_root=False)
        grab_ripple_strips(self.starting_data, self.ripple_strips, self.ripple, ripple_offset)
        if context.scene.vseqf.ripple_markers:
            grab_ripple_markers(self.ripple_markers, self.ripple, ripple_offset)

        if event.type in ['RIGHTMOUSE', 'ESC']:
            #cancel movement and put everything back
            if not self.cancelled:
                self.cancelled = True
                current_frame = context.scene.frame_current
                self.ripple = False
                self.ripple_pop = False
                self.reset_strips()
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

        #when in 'release confirms' mode, blender sometimes sends a 'NONE' event or sometimes just lets the user start moving the mouse ('MOUSEMOVE')... this check might be broken.
        if event.type in ['LEFTMOUSE', 'RET'] or (release_confirm and event.value == 'RELEASE') or (release_confirm and event.type in ['NONE', 'MOUSEMOVE']):
            vu_meter.vu_meter_calculate(context.scene)
            self.remove_draw_handler()
            vseqf.redraw_sequencers()
            if self.prefs.fades:
                fix_fades = True
            else:
                fix_fades = False
            ripple_offset = move_strips(context, self.starting_data, offset_x, offset_y, self.grabbed_strips, ripple_pop=self.ripple_pop, fix_fades=fix_fades, ripple=self.ripple, move_root=False)
            grab_ripple_strips(self.starting_data, self.ripple_strips, self.ripple, ripple_offset)
            if context.scene.vseqf.ripple_markers:
                grab_ripple_markers(self.ripple_markers, self.ripple, ripple_offset)

            if not context.screen.is_animation_playing:
                if self.snap_edge:
                    context.scene.frame_current = self.start_frame
                    context.scene.sequence_editor.overlay_frame = self.start_overlay_frame
                elif self.ripple and self.ripple_pop:
                    context.scene.frame_current = self.ripple_left
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def remove_draw_handler(self):
        bpy.types.SpaceSequenceEditor.draw_handler_remove(self._handle, 'WINDOW')

    def invoke(self, context, event):
        sequencer = context.scene.sequence_editor
        self.start_frame = context.scene.frame_current
        self.start_overlay_frame = sequencer.overlay_frame
        self.cancelled = False
        self.prefs = vseqf.get_prefs()
        region = context.region
        self.view2d = region.view2d
        self.pos_x, self.pos_y = self.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        self.pos_x_start = self.pos_x
        self.pos_y_start = self.pos_y
        self.strips = []
        self.grabbed_strips = []
        self.ripple_strips = []
        strips = timeline.current_strips(context)
        self.timeline_start = timeline.find_strips_start(strips)
        self.timeline_end = timeline.find_strips_end(strips)
        self.ripple_start = self.timeline_end
        self.timeline_height = timeline.find_timeline_height(strips)
        to_move = []
        selected_strips = timeline.current_selected(context)
        for strip in selected_strips:
            if strip.select_right_handle:
                ripple_point = strip.frame_final_end
            else:
                ripple_point = strip.frame_final_start
            if ripple_point < self.ripple_start and not hasattr(strip, 'input_1') and not timeline.is_locked(sequencer, strip):
                self.ripple_start = ripple_point
                self.ripple_left = ripple_point
            to_move.append(strip)

        #store markers to ripple
        self.ripple_markers = []
        for marker in context.scene.timeline_markers:
            if marker.frame >= self.ripple_start:
                self.ripple_markers.append([marker, marker.frame])

        self.starting_data = grab_starting_data(strips)
        #generate grabbed strips and ripple strips lists
        for strip in strips:
            if not timeline.is_locked(sequencer, strip) and not hasattr(strip, 'input_1'):
                self.strips.append(strip)
                if strip.select:
                    self.grabbed_strips.append(strip)
                else:
                    if strip.frame_final_start >= self.ripple_start:
                        self.ripple_strips.append(strip)
        self._timer = context.window_manager.event_timer_add(time_step=0.01, window=context.window)
        self.ripple_strips.sort(key=lambda x: x.frame_final_start)
        self.grabbed_strips.sort(key=lambda x: x.frame_final_start)
        grabbed_left = False
        grabbed_right = False
        grabbed_center = False
        for strip in self.grabbed_strips:
            if strip.select and not (strip.select_left_handle or strip.select_right_handle):
                grabbed_center = strip
            else:
                if strip.select_left_handle:
                    grabbed_left = strip
                if strip.select_right_handle:
                    grabbed_right = strip
        if grabbed_center:
            self.target_grab_variable = 'frame_start'
            self.target_grab_strip = grabbed_center
            self.target_grab_start = grabbed_center.frame_start
            self.target_grab_channel = grabbed_center.channel
        else:
            if grabbed_right:
                self.target_grab_variable = 'frame_final_end'
                self.target_grab_strip = grabbed_right
                self.target_grab_start = grabbed_right.frame_final_end
                self.target_grab_channel = grabbed_right.channel
            if grabbed_left:
                self.target_grab_variable = 'frame_final_start'
                self.target_grab_strip = grabbed_left
                self.target_grab_start = grabbed_left.frame_final_start
                self.target_grab_channel = grabbed_left.channel

        #Determine the snap edges
        if not context.screen.is_animation_playing:
            self.snap_cursor_to_edge = context.scene.vseqf.snap_cursor_to_edge
        else:
            self.snap_cursor_to_edge = False
        self.snap_edge = None
        self.snap_edge_strip = None
        self.secondary_snap_edge = None
        self.secondary_snap_edge_strip = None
        #Determine number of selected edges in grabbed strips:
        selected_edges = []
        for strip in self.grabbed_strips:
            if strip.select_left_handle:
                selected_edges.append([strip, 'left'])
            if strip.select_right_handle:
                selected_edges.append([strip, 'right'])
        if len(selected_edges) == 1:
            #only one edge is grabbed, snap to it
            self.snap_edge_strip = selected_edges[0][0]
            self.snap_edge = selected_edges[0][1]
        elif len(selected_edges) == 2:
            #two strip edges are selected
            #if one strip is active, make that primary
            active = timeline.current_active(context)
            if selected_edges[0][0] == active and selected_edges[1][0] != active:
                self.snap_edge = selected_edges[0][1]
                self.snap_edge_strip = selected_edges[0][0]
                self.secondary_snap_edge = selected_edges[1][1]
                self.secondary_snap_edge_strip = selected_edges[1][0]
            elif selected_edges[1][0] == active and selected_edges[0][0] != active:
                self.snap_edge = selected_edges[1][1]
                self.snap_edge_strip = selected_edges[1][0]
                self.secondary_snap_edge = selected_edges[0][1]
                self.secondary_snap_edge_strip = selected_edges[0][0]
            else:
                #neither strip is active, or both are the same strip, make rightmost primary, leftmost secondary
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
                    self.snap_edge_strip = selected_edges[0][0]
                    self.secondary_snap_edge = selected_edges[1][1]
                    self.secondary_snap_edge_strip = selected_edges[1][0]
                else:
                    self.snap_edge = selected_edges[1][1]
                    self.snap_edge_strip = selected_edges[1][0]
                    self.secondary_snap_edge = selected_edges[0][1]
                    self.secondary_snap_edge_strip = selected_edges[0][0]

        if not self.target_grab_strip:
            #nothing selected... is this possible?
            return {'CANCELLED'}
        if len(self.grabbed_strips) == 1 and not (self.grabbed_strips[0].select_left_handle or self.grabbed_strips[0].select_right_handle):
            self.can_pop = True
        else:
            self.can_pop = False
        context.window_manager.modal_handler_add(self)
        args = (context, )
        self._handle = bpy.types.SpaceSequenceEditor.draw_handler_add(self.vseqf_grab_draw, args, 'WINDOW', 'POST_PIXEL')
        return {'RUNNING_MODAL'}


class VSEQFGrab(bpy.types.Operator):
    """Wrapper operator for the built-in grab operator, runs the added features as well as the original."""
    bl_idname = "vseqf.grab"
    bl_label = "Replacement for the default grab operator with more features"
    bl_options = {"UNDO"}

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
        self.click_mode = get_click_mode(context)
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
        elif active and on_strip(click_frame, click_channel, active):
            #clicked on strip
            active_size = active.frame_final_duration * frame_px
            if abs(click_frame - active.frame_final_start) <= distance * 2 and active_size > 60:
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_strip_left')
            elif abs(click_frame - active.frame_final_end) <= distance * 2 and active_size > 60:
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_strip_right')
            else:
                bpy.ops.wm.call_menu(name="VSEQF_MT_context_strip")
        else:
            is_near_marker = near_marker(context, click_frame, distance)
            if is_near_marker:
                #clicked on marker
                context.scene.vseqf.current_marker_frame = is_near_marker.frame
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_marker')
            else:
                #clicked on empty area
                bpy.ops.wm.call_menu(name='VSEQF_MT_context_none')


class VSEQFDoubleUndo(bpy.types.Operator):
    """Undo previous action"""
    bl_idname = "vseqf.undo"
    bl_label = "Undo previous action"

    def execute(self, context):
        bpy.ops.ed.undo()
        return {'FINISHED'}


class VSEQFContextMarker(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_context_marker'
    bl_label = 'Marker Operations'

    def draw(self, context):
        layout = self.layout
        layout.operator('vseqf.undo', text='Undo')
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
            props = layout.operator('vseqf.quickmarkers_move', text='Move Marker To Cursor')
            props.frame = frame
            props.to_cursor = True


class VSEQFContextCursor(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_cursor"
    bl_label = "Cursor Operations"

    def draw(self, context):
        layout = self.layout
        layout.operator('vseqf.undo', text='Undo')
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
        strip = timeline.current_active(context)
        if strip:
            layout.separator()
            layout.operator('vseqf.quicksnaps', text='Cursor To Beginning Of Strip').type = 'cursor_to_beginning'
            layout.operator('vseqf.quicksnaps', text='Cursor To End Of Strip').type = 'cursor_to_end'
            layout.operator('vseqf.quicksnaps', text='Selected To Cursor').type = 'selection_to_cursor'
            layout.operator('vseqf.quicksnaps', text='Strip Beginning To Cursor').type = 'begin_to_cursor'
            layout.operator('vseqf.quicksnaps', text='Strip End To Cursor').type = 'end_to_cursor'
        markers = context.scene.timeline_markers
        if len(markers) > 0:
            layout.separator()
            layout.operator('vseqf.skip_timeline', text='Jump to Closest Marker').type = 'CLOSEMARKER'
            layout.operator('vseqf.skip_timeline', text='Jump to Previous Marker').type = 'LASTMARKER'
            layout.operator('vseqf.skip_timeline', text='Jump to Next Marker').type = 'NEXTMARKER'


class VSEQFContextNone(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_context_none'
    bl_label = "Operations On Sequence Editor"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator('vseqf.undo', text='Undo')
        layout.separator()
        if timeline.inside_meta_strip():
            layout.operator('vseqf.meta_exit')
            layout.separator()
        layout.menu('SEQUENCER_MT_add')
        layout.menu('VSEQF_MT_quickzooms_menu')
        layout.menu('VSEQF_MT_quicktimeline_menu')


class VSEQFContextStripLeft(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_strip_left"
    bl_label = "Operations On Left Handle"

    def draw(self, context):
        strip = timeline.current_active(context)
        layout = self.layout
        layout.operator('vseqf.undo', text='Undo')
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


class VSEQFContextStripRight(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_strip_right"
    bl_label = "Operations On Right Handle"

    def draw(self, context):
        strip = timeline.current_active(context)
        layout = self.layout
        layout.operator('vseqf.undo', text='Undo')
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


class VSEQFContextStrip(bpy.types.Menu):
    bl_idname = "VSEQF_MT_context_strip"
    bl_label = "Operations On Strip"

    def draw(self, context):
        prefs = vseqf.get_prefs()
        strip = timeline.current_active(context)
        selected = timeline.current_selected(context)
        layout = self.layout
        layout.operator('vseqf.undo', text='Undo')
        if timeline.inside_meta_strip():
            layout.separator()
            layout.operator('vseqf.meta_exit')
        if strip:
            layout.separator()
            layout.label(text='Active Strip:')
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
            layout.label(text='Selected Strip(s):')
            layout.operator('sequencer.meta_make')
            if prefs.cuts:
                layout.menu('VSEQF_MT_quickcuts_menu')
            layout.operator('sequencer.duplicate_move', text='Duplicate')
            layout.operator('vseqf.grab', text='Grab/Move')
