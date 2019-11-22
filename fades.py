import bpy
import bgl
import gpu
from gpu_extras.batch import batch_for_shader
import math
from . import vseqf
from . import timeline


def fix_fades(context, sequence, old_start, old_end):
    fix_fade_in(context, sequence, old_start)
    fix_fade_out(context, sequence, old_end)


def fix_fade_in(context, sequence, old_start):
    if old_start != sequence.frame_final_start:
        # fix fade in
        fade_curve = get_fade_curve(context, sequence, create=False)
        if fade_curve:
            fade_in = fades(fade_curve, sequence, 'detect', 'in', fade_low_point_frame=old_start)
            if fade_in > 0:
                fades(fade_curve, sequence, 'set', 'in', fade_length=fade_in)


def fix_fade_out(context, sequence, old_end):
    if old_end != sequence.frame_final_end:
        # fix fade out
        fade_curve = get_fade_curve(context, sequence, create=False)
        if fade_curve:
            fade_out = fades(fade_curve, sequence, 'detect', 'out', fade_low_point_frame=old_end)
            if fade_out > 0:
                fades(fade_curve, sequence, 'set', 'out', fade_length=fade_out)


def find_crossfade(sequences, first_sequence, second_sequence):
    for sequence in sequences:
        if hasattr(sequence, 'input_1') and hasattr(sequence, 'input_2'):
            if (sequence.input_1 == first_sequence and sequence.input_2 == second_sequence) or (sequence.input_2 == first_sequence and sequence.input_1 == second_sequence):
                return sequence
    return False


def vseqf_crossfade(first_sequence, second_sequence):
    """Add a crossfade between two sequences, the transition type is determined by the vseqf variable 'transition'
    Arguments:
        first_sequence: VSE Sequence object being transitioned from
        second_sequence: VSE Sequence object being transitioned to"""

    transition_type = bpy.context.scene.vseqf.transition
    frame_start = first_sequence.frame_final_end
    frame_end = second_sequence.frame_final_start
    channel = first_sequence.channel
    while timeline.sequencer_area_filled(frame_start, frame_end, channel, channel, []):
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
        if sequence.type == 'SOUND':
            value = sequence.volume
        else:
            value = sequence.blend_alpha
        fade_curve.keyframe_points.add(1)
        point = fade_curve.keyframe_points[0]
        point.co = (sequence.frame_final_start, value)

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

    if not fade_curve:
        return 0
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
    try:
        fade_keyframes = fade_curve.keyframe_points
    except:
        return 0
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
            vseqf.draw_line(strip_left, strip_bottom, fade_in_loc, strip_top, color=(.8, .2, .2, 1))
            vseqf.draw_text(fade_in_loc, strip_top - 12, 11, str(int(fade_in)), color=(1, 1, 1, 1))
        if fade_out > 0:
            strip_right, strip_bottom = view.view_to_region(sequence.frame_final_end, channel_bottom, clip=False)
            fade_out_loc, strip_top = view.view_to_region(sequence.frame_final_end - fade_out, channel_top, clip=False)
            vseqf.draw_line(strip_right, strip_bottom, fade_out_loc, strip_top, color=(.8, .2, .2, 1))
            vseqf.draw_text(fade_out_loc, strip_top - 12, 11, str(int(fade_out)), justify='right', color=(1, 1, 1, 1))


def volume_operator_draw(self, context):
    coords = []
    keyframes = self.curve.keyframe_points
    last_coords = None
    for keyframe in keyframes:
        point = keyframe.co
        ypos = self.active_bottom + (point[1] * self.channel_px)
        xpos = self.active_left + ((point[0] - self.active_strip.frame_final_start) * self.frame_px)
        current_coords = (xpos, ypos)
        if last_coords is not None:
            coords.append(last_coords)
            coords.append(current_coords)
        last_coords = current_coords
    bgl.glEnable(bgl.GL_BLEND)
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {'pos': coords})
    shader.bind()
    shader.uniform_float('color', (1, .5, .5, .5))
    batch.draw(shader)
    bgl.glDisable(bgl.GL_BLEND)


class VSEQFModalVolumeDraw(bpy.types.Operator):
    bl_idname = 'vseqf.volume_draw'
    bl_label = "Draw volume keyframes directly on sound strips in the VSE"

    active_strip = None
    curve = None
    channel_px = 1
    frame_px = 1
    active_left = 0
    active_right = 0
    active_bottom = 0
    active_top = 0
    mode = 'ADD'
    last_press = ''
    last_added = None

    def remove_draw_handler(self, context):
        bpy.types.SpaceSequenceEditor.draw_handler_remove(self._handle, 'WINDOW')
        context.area.header_text_set(None)
        context.workspace.status_text_set(None)

    def update_areas(self, context):
        for area in context.screen.areas:
            if area.type in ['GRAPH_EDITOR', 'SEQUENCE_EDITOR']:
                area.tag_redraw()

    def modal(self, context, event):
        area = context.area
        if event.type in ["V", "MIDDLEMOUSE"] and event.value == 'PRESS':
            if self.mode == 'ADD':
                self.mode = 'REMOVE'
            else:
                self.mode = "ADD"
            return {'RUNNING_MODAL'}
        if self.mode == 'ADD':
            header_text = "Adding keyframes to active strip volume."
        else:
            header_text = "Removing keyframe points from active strip volume"
        area.header_text_set(header_text)
        status_text = "Click and drag on or above the sound strip to add keyframe points.  Press 'V' or MiddleMouse to toggle add/remove mode.  Confirm with Return."
        context.workspace.status_text_set(status_text)

        if event.type in ['LEFTMOUSE', 'MOUSEMOVE']:
            if event.value == 'PRESS' and self.last_press == 'LEFTMOUSE':
                mouse_frame, mouse_channel = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
                clipped_pos_x, clipped_pos_y = context.region.view2d.view_to_region(mouse_frame, mouse_channel)
                if clipped_pos_x == 12000 or clipped_pos_y == 12000:
                    #if the user clicks outside of the area, close the function
                    self.remove_draw_handler(context)
                    return {'FINISHED'}
                mouse_frame = round(mouse_frame)
                if self.mode == 'ADD':
                    if mouse_frame > self.active_strip.frame_final_end:
                        mouse_frame = self.active_strip.frame_final_end
                    if mouse_frame < self.active_strip.frame_final_start:
                        mouse_frame = self.active_strip.frame_final_start
                    if self.last_added is not None and self.last_added != mouse_frame:
                        #Delete points between last_added and current point to prevent spikes in graph
                        low_point = min(self.last_added, mouse_frame)
                        high_point = max(self.last_added, mouse_frame)
                        for frame in range(low_point + 1, high_point):
                            self.active_strip.keyframe_delete('volume', frame=frame)

                    volume = mouse_channel - self.active_strip.channel
                    if volume < 0:
                        volume = 0
                    self.active_strip.keyframe_insert('volume', frame=mouse_frame)
                    for point in self.curve.keyframe_points:
                        if point.co[0] == mouse_frame:
                            point.co[1] = volume
                            point.handle_left[1] = volume
                            point.handle_right[1] = volume
                            self.last_added = mouse_frame
                            break
                else:
                    try:
                        self.active_strip.keyframe_delete('volume', frame=mouse_frame)
                    except:
                        pass
                    context.evaluated_depsgraph_get().update()
            #context.area.tag_redraw()
            self.update_areas(context)

        if event.type == 'LEFTMOUSE':
            self.last_press = 'LEFTMOUSE'
            self.last_added = None
        elif event.type not in ['MOUSEMOVE', 'INBETWEEN_MOUSEMOVE']:
            self.last_press = ''
            self.last_added = None

        if event.type in {'RET'}:
            self.remove_draw_handler(context)
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.remove_draw_handler(context)
            bpy.ops.ed.undo()
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        bpy.ops.ed.undo_push()
        bpy.ops.ed.undo_push()

        #set up necessary variables
        self.mode = 'ADD'
        self.last_press = ''
        self.last_added = None
        active_strip = timeline.current_active(context)
        self.active_strip = active_strip
        if active_strip is None:
            return {'CANCELLED'}
        if active_strip.type != 'SOUND':
            return {'CANCELLED'}
        self.curve = get_fade_curve(context, active_strip, create=True)
        region = bpy.context.region
        view = region.view2d
        #determine pixels per frame and channel
        width = region.width
        height = region.height
        left, bottom = view.region_to_view(0, 0)
        right, top = view.region_to_view(width, height)
        if math.isnan(left):
            return {'CANCELLED'}
        shown_width = right - left
        shown_height = top - bottom
        self.channel_px = height / shown_height
        self.frame_px = width / shown_width
        self.active_left, self.active_top = view.view_to_region(active_strip.frame_final_start, active_strip.channel+1, clip=False)
        self.active_right, self.active_bottom = view.view_to_region(active_strip.frame_final_end, active_strip.channel, clip=False)

        context.window_manager.modal_handler_add(self)
        args = (self, context)
        self._handle = bpy.types.SpaceSequenceEditor.draw_handler_add(volume_operator_draw, args, 'WINDOW', 'POST_PIXEL')
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}


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
                self.value = vseqf.add_to_value(self.value, event.type, is_float=False)

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
                if not get_fade_curve(context, sequence):
                    if sequence.type == 'SOUND':
                        sequence.volume = 1
                    else:
                        sequence.blend_alpha = 1

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
    bl_label = "Quick Fades"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Sequencer"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()
        try:
            #Check for an active sequence to operate on
            sequence = timeline.current_active(context)
            if sequence:
                return prefs.fades
            else:
                return False

        except:
            return False

    def draw(self, context):
        #Set up basic variables needed by panel
        scene = bpy.context.scene
        active_sequence = timeline.current_active(context)
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
        row.prop(scene.vseqf, 'fade')
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
        row.prop(scene.vseqf, 'transition')
        row = layout.row(align=True)
        row.operator('vseqf.quickfades_cross', text='Crossfade Prev Clip', icon='BACK').type = 'previous'
        row.operator('vseqf.quickfades_cross', text='Crossfade Next Clip', icon='FORWARD').type = 'next'
        row = layout.row(align=True)
        row.operator('vseqf.quickfades_cross', text='Smart Cross to Prev', icon='BACK').type = 'previoussmart'
        row.operator('vseqf.quickfades_cross', text='Smart Cross to Next', icon='FORWARD').type = 'nextsmart'


class VSEQF_PT_QuickFadesStripPanel(bpy.types.Panel):
    """Panel for QuickFades properties."""
    bl_label = "Fades"
    bl_parent_id = "SEQUENCER_PT_adjust"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()
        try:
            #Check for an active sequence to operate on
            sequence = timeline.current_active(context)
            if sequence:
                return prefs.fades
            else:
                return False

        except:
            return False

    def draw(self, context):
        #Set up basic variables needed by panel
        scene = bpy.context.scene
        active_sequence = timeline.current_active(context)
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


class VSEQFQuickFadesMenu(bpy.types.Menu):
    """Pop-up menu for QuickFade operators"""
    bl_idname = "VSEQF_MT_quickfades_menu"
    bl_label = "Quick Fades"

    @classmethod
    def poll(cls, context):
        del context
        prefs = vseqf.get_prefs()
        return prefs.fades

    def draw(self, context):
        scene = context.scene
        sequences = timeline.current_selected(context)
        sequence = timeline.current_active(context)

        layout = self.layout
        if sequence and len(sequences) > 0:
            #If a sequence is active
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
            layout.prop(scene.vseqf, 'fade')
            layout.operator('vseqf.quickfades_set', text='Set Fadein').type = 'in'
            layout.operator('vseqf.quickfades_set', text='Set Fadeout').type = 'out'
            layout.operator('vseqf.quickfades_clear', text='Clear Fades').direction = 'both'

            #Add crossfades
            layout.separator()
            layout.prop(scene.vseqf, 'transition', text='')
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
        selected_sequences = timeline.current_selected(context)
        for sequence in selected_sequences:
            fade_curve = get_fade_curve(context, sequence, create=True)
            if self.type == 'both':
                fades(fade_curve, sequence, 'set', 'in', fade_length=context.scene.vseqf.fade)
                fades(fade_curve, sequence, 'set', 'out', fade_length=context.scene.vseqf.fade)
            else:
                fades(fade_curve, sequence, 'set', self.type, fade_length=context.scene.vseqf.fade)
            if not get_fade_curve(context, sequence):
                if sequence.type == 'SOUND':
                    sequence.volume = 1
                else:
                    sequence.blend_alpha = 1

        vseqf.redraw_sequencers()
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
            sequences = [timeline.current_active(context)]
        else:
            sequences = timeline.current_selected(context)

        for sequence in sequences:
            fade_curve = get_fade_curve(context, sequence, create=False)
            #iterate through selected sequences and remove fades
            if fade_curve:
                if self.direction != 'both':
                    fades(fade_curve, sequence, 'set', self.direction, fade_length=0)
                else:
                    fades(fade_curve, sequence, 'set', 'in', fade_length=0)
                    fades(fade_curve, sequence, 'set', 'out', fade_length=0)
                if sequence.type == 'SOUND':
                    sequence.volume = 1
                else:
                    sequence.blend_alpha = 1

        vseqf.redraw_sequencers()
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
        sequences = timeline.current_sequences(context)

        #store a list of selected sequences since adding a crossfade destroys the selection
        selected_sequences = timeline.current_selected(context)
        active_sequence = timeline.current_active(context)

        for sequence in selected_sequences:
            if sequence.type != 'SOUND' and not hasattr(sequence, 'input_1'):
                bpy.ops.ed.undo_push()
                first_sequence = None
                second_sequence = None
                #iterate through selected sequences and add crossfades to previous or next sequence
                if self.type == 'nextsmart':
                    #Need to find next sequence
                    first_sequence = sequence
                    second_sequence = timeline.find_close_sequence(sequences, first_sequence, 'next', mode='all')
                elif self.type == 'previoussmart':
                    #Need to find previous sequence
                    second_sequence = sequence
                    first_sequence = timeline.find_close_sequence(sequences, second_sequence, 'previous', mode='all')
                elif self.type == 'next':
                    #Need to find next sequence
                    first_sequence = sequence
                    second_sequence = timeline.find_close_sequence(sequences, first_sequence, 'next', mode='all')
                elif self.type == 'previous':
                    #Need to find previous sequence
                    second_sequence = sequence
                    first_sequence = timeline.find_close_sequence(sequences, second_sequence, 'previous', mode='all')
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
