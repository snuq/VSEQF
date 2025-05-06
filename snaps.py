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
        props = layout.operator("sequencer.strip_jump", text="Jump to Previous Strip")
        props.next = False
        props.center = False
        props = layout.operator("sequencer.strip_jump", text="Jump to Next Strip")
        props.next = True
        props.center = False
        try:
            #Display only if active strip is set
            strip = timeline.current_active(context)
            if strip:
                props = layout.operator('vseqf.quicksnaps', text='Cursor To Beginning Of Active')
                props.type = 'cursor_to_beginning'
                props.tooltip = 'Moves the cursor to the beginning of the active strip'
                props = layout.operator('vseqf.quicksnaps', text='Cursor To End Of Active')
                props.type = 'cursor_to_end'
                props.tooltip = 'Moves the cursor to the end of the active strip'
                layout.separator()
                props = layout.operator('vseqf.quicksnaps', text='Selected To Cursor')
                props.type = 'selection_to_cursor'
                props.tooltip = 'Snaps the strip edges or strip beginning to the cursor'
                layout.separator()
                props = layout.operator('vseqf.quicksnaps', text='Selected Beginnings To Cursor')
                props.type = 'begin_to_cursor'
                props.tooltip = 'Moves the beginning of selected strips to the cursor position'
                props = layout.operator('vseqf.quicksnaps', text='Selected Ends To Cursor')
                props.type = 'end_to_cursor'
                props.tooltip = 'Moves the ending of selected strips to the cursor position'
                props = layout.operator('vseqf.quicksnaps', text='Selected To Previous Strip')
                props.type = 'strip_to_previous'
                props.tooltip = 'Snaps the active strip to the closest previous strip'
                props = layout.operator('vseqf.quicksnaps', text='Selected To Next Strip')
                props.type = 'strip_to_next'
                props.tooltip = 'Snaps the active strip to the closest next strip'
                props = layout.operator('vseqf.quicksnaps', text='Selected Ripple To Cursor')
                props.type = 'strip_ripple'
                props.tooltip = 'Snaps all strips to the cursor as if they were one strip'
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
    """Operator for snapping the cursor and strips
    Argument:
        type: String, snapping operation to perform
            'cursor_to_seconds': Rounds the cursor position to the nearest second
            'cursor_to_beginning': Moves the cursor to the beginning of the active strip
            'cursor_to_end': Moves the cursor to the end of the active strip

            'begin_to_cursor': Moves the beginning of selected strips to the cursor position
            'end_to_cursor': Moves the ending of selected strips to the cursor position
            'strip_to_previous': Snaps the active strip to the closest previous strip
            'strip_to_next': Snaps the active strip to the closest next strip
            'selection_to_cursor': Snaps the strip edges or strip beginning to the cursor
            'strip_ripple': Snaps all strips to the cursor as if they were one strip"""

    bl_idname = 'vseqf.quicksnaps'
    bl_label = 'VSEQF Quick Snaps'
    bl_description = 'Snaps selected strips'

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
        strips = timeline.current_strips(context)

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

        #strip snaps
        else:
            to_snap = []
            for strip in strips:
                if strip.select and not hasattr(strip, 'input_1') and not timeline.is_locked(sequencer, strip):
                    to_snap.append(strip)

            if not to_snap:
                self.report({'WARNING'}, 'Nothing To Snap')
                return{'CANCELLED'}

            to_snap.sort(key=lambda x: x.frame_final_start)
            starting_data = grabs.grab_starting_data(strips)

            if self.type == 'begin_to_cursor':
                snap_target = context.scene.frame_current
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for strip in to_snap:
                    offset_x = (snap_target - strip.frame_final_start)
                    grabs.move_strips(context, starting_data, offset_x, 0, [strip])

            elif self.type == 'end_to_cursor':
                snap_target = context.scene.frame_current
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for strip in to_snap:
                    offset_x = (snap_target - strip.frame_final_end)
                    grabs.move_strips(context, starting_data, offset_x, 0, [strip])

            elif self.type == 'strip_to_previous':
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for strip in to_snap:
                    previous = timeline.find_close_strip(strips, strip, 'previous', 'nooverlap', sounds=True)
                    if previous:
                        offset_x = (previous.frame_final_end - strip.frame_final_start)
                        grabs.move_strips(context, starting_data, offset_x, 0, [strip])
                    else:
                        self.report({'WARNING'}, 'No Previous Strip Found')

            elif self.type == 'strip_to_next':
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                for strip in to_snap:
                    next_seq = timeline.find_close_strip(strips, strip, 'next', 'nooverlap', sounds=True)
                    if next_seq:
                        offset_x = (next_seq.frame_final_start - strip.frame_final_end)
                        grabs.move_strips(context, starting_data, offset_x, 0, [strip])
                    else:
                        self.report({'WARNING'}, 'No Next Strip Found')

            elif self.type == 'selection_to_cursor':
                snap_target = context.scene.frame_current
                check_snap = []
                for strip in to_snap:
                    if strip.select_right_handle and not strip.select_left_handle:
                        snap_start = strip.frame_final_end
                    else:
                        snap_start = strip.frame_final_start
                    offset_x = (snap_target - snap_start)
                    grabs.move_strips(context, starting_data, offset_x, 0, [strip], fix_fades=True)
                    check_snap.append([strip, offset_x])
                for data in check_snap:
                    #Check positions again because the strip collisions thing can mess them up
                    strip = data[0]
                    offset_x = data[1]
                    grabs.move_strips(context, starting_data, offset_x, 0, [strip])

            elif self.type == 'strip_ripple':
                for data in starting_data:
                    #Ensure that no handles are moved
                    starting_data[data].select_left_handle = False
                    starting_data[data].select_right_handle = False
                start = to_snap[0]
                for strip in to_snap:
                    if strip.frame_final_start < start.frame_final_start:
                        start = strip
                snap_target = context.scene.frame_current
                offset_x = (snap_target - start.frame_final_start)
                grabs.move_strips(context, starting_data, offset_x, 0, to_snap)

        return{'FINISHED'}
