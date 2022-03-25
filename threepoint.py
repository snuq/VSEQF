import bpy
import os
from . import timeline
from . import parenting
from . import vseqf


def update_import_frame_in(self, fps):
    self.import_frame_in = int(round((self.import_minutes_in * 60 * fps) + (self.import_seconds_in * fps) + self.import_frames_in))


def update_import_frame_length(self, fps):
    self.import_frame_length = int(round((self.import_minutes_length * 60 * fps) + (self.import_seconds_length * fps) + self.import_frames_length))


def update_import_minutes_in(self, context):
    fps = vseqf.get_fps(context.scene)
    length = self.full_length
    length_timecode = vseqf.timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length > max_minutes:
        if self.import_minutes_length > 0:
            self.import_minutes_length = self.import_minutes_length - 1
        else:
            self.import_minutes_in = self.import_minutes_in - 1
    update_import_frame_in(self, fps)


def update_import_minutes_length(self, context):
    fps = vseqf.get_fps(context.scene)
    length = self.full_length
    length_timecode = vseqf.timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length > max_minutes:
        self.import_minutes_length = self.import_minutes_length - 1
    update_import_frame_length(self, fps)


def update_import_seconds_in(self, context):
    fps = vseqf.get_fps(context.scene)
    length = self.full_length
    length_timecode = vseqf.timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
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
    fps = vseqf.get_fps(context.scene)
    length = self.full_length
    length_timecode = vseqf.timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
    max_hours, max_minutes, max_seconds, max_frames = length_timecode
    max_minutes = max_minutes + (max_hours * 60)
    if self.import_minutes_in + self.import_minutes_length >= max_minutes:
        if self.import_seconds_length + self.import_seconds_in > max_seconds:
            self.import_seconds_length = int(round(max_seconds - self.import_seconds_in))
    else:
        if self.import_seconds_length >= 60:
            self.import_seconds_length = 0
            self.import_minutes_length = int(round(self.import_minutes_length + 1))
    update_import_frame_length(self, fps)


def update_import_frames_in(self, context):
    fps = vseqf.get_fps(context.scene)
    length = self.full_length
    length_timecode = vseqf.timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
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
                self.import_frames_length = int(round(fps) - 1)
            elif self.import_frames_length > 1:
                #reduce frame length
                self.import_frames_length = self.import_frames_length - 1
            elif self.import_frames_in + self.import_frames_length >= fps - 1:
                #everything is maxed out, hold at maximum
                self.import_frames_in = max_frames - 1
    update_import_frame_in(self, fps)


def update_import_frames_length(self, context):
    fps = vseqf.get_fps(context.scene)
    length = self.full_length
    length_timecode = vseqf.timecode_from_frames(length, fps, subsecond_type='frames', mode='list')
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
    vseqf.draw_rect(0, height - double_scale, width, double_scale, colorbg)
    vseqf.draw_rect(0, height - half_scale - 2, width, 4, colormg)
    vseqf.draw_rect(0, height - scale - half_scale - 2, width, 4, colormg)
    vseqf.draw_rect(0, height - scale - 1, width, 2, colormg)

    #draw in/out icons
    in_x = self.in_percent * width
    vseqf.draw_rect(in_x, height - scale, quarter_scale, scale, colorfg)
    vseqf.draw_tri((in_x, height - half_scale), (in_x + half_scale, height), (in_x + half_scale, height - scale), colorfg)

    if self.in_percent <= .5:
        in_text_x = in_x + scale
    else:
        in_text_x = 0 + half_scale
    vseqf.draw_text(in_text_x, height - scale + 2, scale - 2, "In: "+str(self.in_frame), colorfg)

    out_x = self.out_percent * width
    vseqf.draw_rect(out_x - quarter_scale, height - double_scale, quarter_scale, scale, colorfg)
    vseqf.draw_tri((out_x, height - half_scale - scale), (out_x - half_scale, height - scale), (out_x - half_scale, height - double_scale), colorfg)
    if self.out_percent >= .5:
        out_text_x = 0 + half_scale
    else:
        out_text_x = out_x + half_scale
    vseqf.draw_text(out_text_x, height - double_scale + 2, scale - 2, "Length: "+str(self.out_frame - self.in_frame), colorfg)


class VSEQF_PT_ThreePointBrowserPanel(bpy.types.Panel):
    bl_label = "3Point Edit"
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOLS'
    bl_category = "Quick 3Point"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()
        if not prefs.threepoint:
            return False
        params = context.space_data.params
        selected_file = params.filename
        if selected_file:
            filename, extension = os.path.splitext(selected_file)
            if extension.lower() in bpy.path.extensions_movie:
                directory = params.directory.decode("utf-8")  #uhh... apparently this is now a bytes string?? what.
                full_filename = os.path.join(directory, params.filename)
                if os.path.exists(full_filename):
                    return True
        return False

    def draw(self, context):
        del context
        layout = self.layout
        row = layout.row()
        row.operator('vseqf.threepoint_import_to_clip', text='Import To Clip Editor')


class ThreePointSetup:
    clip = None
    iterations = 0

    def threepoint_setup_area(self, *_):
        self.iterations += 1
        areas = bpy.context.screen.areas
        if len(areas) > 1 or areas[0].type != 'FILE_BROWSER':
            #check if areas have changed
            for area in areas:
                if area.type == 'CLIP_EDITOR':
                    for space in area.spaces:
                        if space.type == 'CLIP_EDITOR':
                            space.clip = self.clip
                            override = bpy.context.copy()
                            override['area'] = area
                            override['space_data'] = space
                            if bpy.context.scene.vseqf.build_proxy:
                                bpy.ops.clip.rebuild_proxy(override)
            self.remove_handler()
            return

        if self.iterations > 20:
            #prevent infinite loop
            self.remove_handler()

    def remove_handler(self):
        handlers = bpy.app.handlers.depsgraph_update_post
        for handler in handlers:
            if " threepoint_setup_area " in str(handler):
                handlers.remove(handler)


class VSEQFThreePointImportToClip(bpy.types.Operator):
    bl_idname = "vseqf.threepoint_import_to_clip"
    bl_label = "Import Movie To Clip Editor"
    bl_description = 'Creates a movieclip from the selected video file and sets any visible Movie Clip Editor area to display it'

    _timer = None
    clip = None
    tries = 0

    def execute(self, context):
        self.tries = 0
        params = context.space_data.params
        directory = params.directory.decode("utf-8")  #uhh... apparently this is now a bytes string?? what.
        filename = os.path.join(directory, params.filename)
        self.clip = bpy.data.movieclips.load(filename, check_existing=True)
        if len(context.screen.areas) == 1 and context.screen.areas[0].type == 'FILE_BROWSER':
            #User is using the fullscreen file browser, close it
            bpy.ops.file.cancel()

            clip = self.clip
            proxy = vseqf.proxy()
            if proxy:
                vseqf.apply_proxy_settings(clip)

            handlers = bpy.app.handlers.depsgraph_update_post
            for handler in handlers:
                if " threepoint_setup_area " in str(handler):
                    handlers.remove(handler)
            threepointsetup = ThreePointSetup()
            threepointsetup.clip = clip
            handlers.append(threepointsetup.threepoint_setup_area)
            return {'RUNNING_MODAL'}

        return {'FINISHED'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)


class VSEQF_PT_ThreePointPanel(bpy.types.Panel):
    bl_label = "3 Point Edit"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Footage"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()
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
        scene = context.scene

        row = layout.row()
        row.operator('vseqf.threepoint_modal_operator', text='Set In/Out')
        fps = vseqf.get_fps(context.scene)
        row = layout.row()
        if clip.import_settings.import_frame_in != -1:
            row.label(text="In: "+str(clip.import_settings.import_frame_in)+' ('+vseqf.timecode_from_frames(clip.import_settings.import_frame_in, fps)+')')
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
            row.label(text="Length: "+str(clip.import_settings.import_frame_length)+' ('+vseqf.timecode_from_frames(clip.import_settings.import_frame_length, fps)+')')
        else:
            row.label(text="Length Not Set")
        row = layout.row()
        prop = row.operator('vseqf.threepoint_import', text='Import At Cursor')
        prop.type = 'cursor'
        prop.tooltip = "Import this video into the VSE at frame "+str(scene.frame_current)
        row = layout.row()
        prop = row.operator('vseqf.threepoint_import', text='Replace Active Sequence')
        prop.type = 'replace'
        prop.tooltip = "Import this video into the VSE and replace the active sequence"
        row = layout.row()
        prop = row.operator('vseqf.threepoint_import', text='Insert At Cursor')
        prop.type = 'insert'
        prop.tooltip = "Import and insert this video into the VSE at frame "+str(scene.frame_current)
        row = layout.row()
        prop = row.operator('vseqf.threepoint_import', text='Cut Insert At Cursor')
        prop.type = 'cut_insert'
        prop.tooltip = "Cut all sequences at frame "+str(scene.frame_current)+" and insert this videoe"
        row = layout.row()
        prop = row.operator('vseqf.threepoint_import', text='Import At End')
        prop.type = 'end'
        prop.tooltip = "Import this video into the VSE at the end of all sequences"


class VSEQFThreePointImport(bpy.types.Operator):
    bl_idname = "vseqf.threepoint_import"
    bl_label = "Imports a movie clip into the VSE as a movie sequence"

    type: bpy.props.StringProperty()
    tooltip: bpy.props.StringProperty("Import a movie clip into the VSE s a movie sequence")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

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
            active_strip = timeline.current_active(context)
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
            frame_start = timeline.find_sequences_start(sequences) - clip.frame_duration - 1
            bpy.ops.sequencer.movie_strip_add(override, filepath=filepath, frame_start=frame_start, replace_sel=True, use_framerate=False)
            sound_sequence = False
            movie_sequence = False
            sequences = context.scene.sequence_editor.sequences_all
            selected = timeline.current_selected(context)
            for seq in selected:
                if seq.type == 'MOVIE':
                    movie_sequence = seq
                if seq.type == 'SOUND':
                    sound_sequence = seq
            if not movie_sequence:
                return {'CANCELLED'}
            if movie_sequence and sound_sequence:
                #Attempt to fix a blender bug where it puts the audio strip too low - https://developer.blender.org/T64964
                frame_start_backup = movie_sequence.frame_start
                sound_channel = movie_sequence.channel
                movie_sequence.channel = movie_sequence.channel + 1
                movie_sequence.frame_start = frame_start_backup
                sound_sequence.channel = sound_channel

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
                children = parenting.find_children(active_strip)
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
                    #Have to set the frame_current because for some reason the frame variable in vseqf.cut doesnt work...
                    old_current = context.scene.frame_current
                    context.scene.frame_current = move_frame
                    bpy.ops.vseqf.cut(type='INSERT_ONLY', use_insert=True, insert=move_forward, use_all=True, all=True)
                    context.scene.frame_current = old_current
                for child in children:
                    child.parent = movie_sequence.name
            elif self.type == 'end':
                import_pos = timeline.find_sequences_end(sequences)
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
        fps = round(vseqf.get_fps(context.scene))
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
        update=update_import_minutes_in,
        description="Minutes to remove from beginning of video when importing")
    import_seconds_in: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_seconds_in,
        description="Seconds to remove from beginning of video when importing")
    import_frames_in: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_frames_in,
        description="Frames to remove from beginning of video when importing")
    import_minutes_length: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_minutes_length,
        description="Minutes component of imported video length")
    import_seconds_length: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_seconds_length,
        description="Seconds component of imported video length")
    import_frames_length: bpy.props.IntProperty(
        default=0,
        min=0,
        update=update_import_frames_length,
        description="Frames component of imported video length")
