import bpy
from . import timeline
from . import vseqf
from . import grabs
from . import shortcuts


class VSEQFQuickSnapsMenu(bpy.types.Menu):
    """QuickSnaps pop-up menu listing snapping operators"""
    bl_idname = "VSEQF_MT_quicksnaps_menu"
    bl_label = "Quick Snaps"

    def draw(self, context):
        layout = self.layout
        props = layout.operator('vseqf.quicksnaps', text='Cursor To Nearest Second')
        props.type = 'cursor_to_seconds'
        props.tooltip = 'Rounds the cursor position to the nearest second'
        props = layout.operator("sequencer.strip_jump", text="Jump to Previous Sequence")
        props.next = False
        props.center = False
        props = layout.operator("sequencer.strip_jump", text="Jump to Next Sequence")
        props.next = True
        props.center = False
        try:
            #Display only if active sequence is set
            sequence = timeline.current_active(context)
            if sequence:
                props = layout.operator('vseqf.quicksnaps', text='Cursor To Beginning Of Active')
                props.type = 'cursor_to_beginning'
                props.tooltip = 'Moves the cursor to the beginning of the active sequence'
                props = layout.operator('vseqf.quicksnaps', text='Cursor To End Of Active')
                props.type = 'cursor_to_end'
                props.tooltip = 'Moves the cursor to the end of the active sequence'
                layout.separator()
                props = layout.operator('vseqf.quicksnaps', text='Selected To Cursor')
                props.type = 'selection_to_cursor'
                props.tooltip = 'Snaps the sequence edges or sequence beginning to the cursor'
                layout.separator()
                props = layout.operator('vseqf.quicksnaps', text='Selected Beginnings To Cursor')
                props.type = 'begin_to_cursor'
                props.tooltip = 'Moves the beginning of selected sequences to the cursor position'
                props = layout.operator('vseqf.quicksnaps', text='Selected Ends To Cursor')
                props.type = 'end_to_cursor'
                props.tooltip = 'Moves the ending of selected sequences to the cursor position'
                props = layout.operator('vseqf.quicksnaps', text='Selected To Previous Sequence')
                props.type = 'sequence_to_previous'
                props.tooltip = 'Snaps the active sequence to the closest previous sequence'
                props = layout.operator('vseqf.quicksnaps', text='Selected To Next Sequence')
                props.type = 'sequence_to_next'
                props.tooltip = 'Snaps the active sequence to the closest next sequence'
                props = layout.operator('vseqf.quicksnaps', text='Selected Ripple To Cursor')
                props.type = 'sequence_ripple'
                props.tooltip = 'Snaps all sequences to the cursor as if they were one sequence'
        except:
            pass
        markers = context.scene.timeline_markers
        if len(markers) > 0:
            layout.separator()
            props = layout.operator('vseqf.skip_timeline', text='Jump to Closest Marker')
            props.type = 'CLOSEMARKER'
            props.tooltip = 'Snaps the cursor to the nearest timeline marker'
            props = layout.operator('vseqf.skip_timeline', text='Jump to Previous Marker')
            props.type = 'LASTMARKER'
            props.tooltip = 'Snaps the cursor to the previous timeline marker'
            props = layout.operator('vseqf.skip_timeline', text='Jump to Next Marker')
            props.type = 'NEXTMARKER'
            props.tooltip = 'Snaps the cursor to the next timehline marker'
            props = layout.operator('vseqf.quicksnaps', text='Closest Marker to Cursor')
            props.type = 'marker_to_cursor'
            props.tooltip = 'Snaps the closest marker to the cursor position'


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
            'selection_to_cursor': Snaps the sequence edges or sequence beginning to the cursor
            'sequence_ripple': Snaps all sequences to the cursor as if they were one sequence"""

    bl_idname = 'vseqf.quicksnaps'
    bl_label = 'VSEQF Quick Snaps'
    bl_description = 'Snaps selected sequences'

    type: bpy.props.StringProperty()
    tooltip: bpy.props.StringProperty("")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):
        bpy.ops.ed.undo_push()
        #Set up variables needed for operator
        sequencer = context.scene.sequence_editor
        selected = timeline.current_selected(context)
        scene = context.scene
        active = timeline.current_active(context)
        sequences = timeline.current_sequences(context)

        #Cursor snaps
        if self.type == 'cursor_to_seconds':
            fps = vseqf.get_fps(scene)
            scene.frame_current = int(round(round(scene.frame_current / fps) * fps))
        elif self.type == 'cursor_to_beginning':
            if active:
                scene.frame_current = active.frame_final_start
        elif self.type == 'cursor_to_end':
            if active:
                scene.frame_current = active.frame_final_end

        #Marker snaps
        elif self.type == 'marker_to_cursor':
            closest_marker = shortcuts.find_marker(scene.frame_current, 'closest')
            if closest_marker is not None:
                closest_marker.frame = scene.frame_current

        #Sequence snaps
        else:
            to_snap = []
            for sequence in sequences:
                if sequence.select and not hasattr(sequence, 'input_1') and not timeline.is_locked(sequencer, sequence):
                    to_snap.append(sequence)

            if not to_snap:
                self.report({'WARNING'}, 'Nothing To Snap')
                return{'CANCELLED'}

            to_snap.sort(key=lambda x: x.frame_final_start)
            starting_data = grabs.grab_starting_data(sequences)

            if self.type == 'begin_to_cursor':
                snap_target = context.scene.frame_current
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for sequence in to_snap:
                    offset_x = (snap_target - sequence.frame_final_start)
                    grabs.move_sequences(context, starting_data, offset_x, 0, [sequence])

            elif self.type == 'end_to_cursor':
                snap_target = context.scene.frame_current
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for sequence in to_snap:
                    offset_x = (snap_target - sequence.frame_final_end)
                    grabs.move_sequences(context, starting_data, offset_x, 0, [sequence])

            elif self.type == 'sequence_to_previous':
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for sequence in to_snap:
                    previous = timeline.find_close_sequence(sequences, sequence, 'previous', 'nooverlap', sounds=True)
                    if previous:
                        offset_x = (previous.frame_final_end - sequence.frame_final_start)
                        grabs.move_sequences(context, starting_data, offset_x, 0, [sequence])
                    else:
                        self.report({'WARNING'}, 'No Previous Sequence Found')

            elif self.type == 'sequence_to_next':
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for sequence in to_snap:
                    next_seq = timeline.find_close_sequence(sequences, sequence, 'next', 'nooverlap', sounds=True)
                    if next_seq:
                        offset_x = (next_seq.frame_final_start - sequence.frame_final_end)
                        grabs.move_sequences(context, starting_data, offset_x, 0, [sequence])
                    else:
                        self.report({'WARNING'}, 'No Next Sequence Found')

            elif self.type == 'selection_to_cursor':
                snap_target = context.scene.frame_current
                check_snap = []
                for sequence in to_snap:
                    if sequence.select_right_handle and not sequence.select_left_handle:
                        snap_start = sequence.frame_final_end
                    else:
                        snap_start = sequence.frame_final_start
                    offset_x = (snap_target - snap_start)
                    grabs.move_sequences(context, starting_data, offset_x, 0, [sequence], fix_fades=True)
                    check_snap.append([sequence, offset_x])
                for data in check_snap:
                    #Check positions again because the strip collisions thing can mess them up
                    sequence = data[0]
                    offset_x = data[1]
                    grabs.move_sequences(context, starting_data, offset_x, 0, [sequence])

            elif self.type == 'sequence_ripple':
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                start = to_snap[0]
                for sequence in to_snap:
                    if sequence.frame_final_start < start.frame_final_start:
                        start = sequence
                snap_target = context.scene.frame_current
                offset_x = (snap_target - start.frame_final_start)
                grabs.move_sequences(context, starting_data, offset_x, 0, to_snap)

        return{'FINISHED'}
