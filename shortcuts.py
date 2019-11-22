import bpy
from . import parenting
from . import vseqf


def nudge_selected(frame=0, channel=0):
    """Moves the selected sequences by a given amount."""

    to_nudge = []
    for sequence in bpy.context.selected_sequences:
        if vseqf.parenting():
            parenting.get_recursive(sequence, to_nudge)
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
        second = int(round(vseqf.get_fps(context.scene)))
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
        shortcut_skip = context.scene.vseqf.shortcut_skip
        if shortcut_skip == 0:
            second_frames = int(round(vseqf.get_fps(context.scene)))
        else:
            second_frames = shortcut_skip

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


