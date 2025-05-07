import bpy
from . import timeline
from . import grabs
from . import vseqf


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
    bl_label = "Wrapper for the built in strip cut operator that provides extra cut operations."
    bl_options = {"UNDO"}

    tooltip: bpy.props.StringProperty("Cut the selected strips")
    use_frame: bpy.props.BoolProperty(default=False)  #when true, use the passed-in frame value, use current scene frame otherwise
    frame = bpy.props.IntProperty(0)
    type: bpy.props.EnumProperty(name='Type', items=[("SOFT", "Soft", "", 1), ("HARD", "Hard", "", 2), ("INSERT", "Insert Cut", "", 3), ("INSERT_ONLY", "Insert Only", "", 4), ("TRIM", "Trim", "", 5), ("TRIM_LEFT", "Trim Left", "", 6), ("TRIM_RIGHT", "Trim Right", "", 7), ("SLIDE", "Slide", "", 8), ("SLIDE_LEFT", "Slide Left", "", 9), ("SLIDE_RIGHT", "Slide Right", "", 10), ("RIPPLE", "Ripple", "", 11), ("RIPPLE_LEFT", "Ripple Left", "", 12), ("RIPPLE_RIGHT", "Ripple Right", "", 13), ("UNCUT", "UnCut", "", 14), ("UNCUT_LEFT", "UnCut Left", "", 15), ("UNCUT_RIGHT", "UnCut Right", "", 16)], default='SOFT')
    side: bpy.props.EnumProperty(name='Side', items=[("BOTH", "Both", "", 1), ("RIGHT", "Right", "", 2), ("LEFT", "Left", "", 3)], default='BOTH')
    all: bpy.props.BoolProperty(name='Cut All', default=False)
    use_all: bpy.props.BoolProperty(default=False)  #when true, use passed-in all option, ignore the vseqf default
    insert: bpy.props.IntProperty(0)
    use_insert: bpy.props.BoolProperty(default=False)  #when true, use the passed-in insert option, ignore the vseqf default

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

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

    def delete_strip(self, strip):
        """Deletes a strip while maintaining previous selected and active strips
        Argument:
            strip: VSE strip object to delete"""

        active = timeline.current_active(bpy.context)
        selected = []
        for seq in bpy.context.scene.sequence_editor.strips:
            if seq.select:
                selected.append(seq)
                seq.select = False
        strip.select = True
        bpy.ops.sequencer.delete()
        for seq in selected:
            seq.select = True
        if active:
            bpy.context.scene.sequence_editor.active_strip = active

    def check_source(self, strip, next_strip):
        """Used by UnCut, checks the source and position of two strips to see if they can be merged

        Arguments:
            strip: VSE Strip object to be compared
            next_strip: VSE Strip object to be compared

        Returns: Boolean"""

        if strip.type == next_strip.type:
            if strip.type == 'IMAGE':
                if strip.directory == next_strip.directory and strip.elements[0].filename == next_strip.elements[0].filename:
                    if len(strip.elements) == 1 and len(next_strip.elements) == 1:
                        return True
                    elif strip.frame_start == next_strip.frame_start:
                        return True
            elif strip.frame_start == next_strip.frame_start:
                if strip.type == 'SOUND':
                    if strip.sound.filepath == next_strip.sound.filepath:
                        return True
                if strip.type == 'MOVIE':
                    if strip.filepath == next_strip.filepath:
                        return True
                if strip.type == 'SCENE':
                    if strip.scene == next_strip.scene:
                        return True
                if strip.type == 'MOVIECLIP':

                    #no way of checking source file :\
                    pass
        return False

    def execute(self, context):
        if self.use_frame:
            cut_frame = self.frame
        else:
            cut_frame = context.scene.frame_current
        status = self.start_cut(context, cut_frame)
        self.reset()
        return status

    def invoke(self, context, event):
        if self.use_frame:
            cut_frame = self.frame
        else:
            cut_frame = context.scene.frame_current
        mouse_x = event.mouse_region_x
        region = context.region
        view = region.view2d
        cursor, bottom = view.view_to_region(cut_frame, 0, clip=False)
        if mouse_x < cursor:
            side = 'LEFT'
        else:
            side = 'RIGHT'
        status = self.start_cut(context, cut_frame, side)
        self.reset()
        return status

    def uncut(self, context, side="BOTH"):
        #merges a strip to the one on the left or right if they share the same source and position
        if side == 'BOTH':
            return{"CANCELLED"}

        sequencer = context.scene.sequence_editor
        selected = timeline.current_selected(context)
        to_uncut = []
        for strip in selected:
            if not timeline.is_locked(sequencer, strip) and not hasattr(strip, 'input_1'):
                to_uncut.append(strip)
        for strip in to_uncut:
            if side == 'LEFT':
                direction = 'previous'
            else:
                direction = 'next'
            strips = timeline.current_strips(context)
            merge_to = timeline.find_close_strip(strips, strip, direction=direction, mode='channel', sounds=True)
            if merge_to:
                if not timeline.is_locked(sequencer, merge_to):
                    source_matches = self.check_source(strip, merge_to)
                    if source_matches:
                        if direction == 'next':
                            newend = merge_to.frame_final_end
                            self.delete_strip(merge_to)
                            strip.frame_final_end = newend
                        else:
                            newstart = merge_to.frame_final_start
                            self.delete_strip(merge_to)
                            strip.frame_final_start = newstart
        return{'FINISHED'}

    def do_insert(self, context, cut_frame):
        if self.use_insert:
            insert = self.insert
        else:
            insert = context.scene.vseqf.quickcuts_insert
        strips = timeline.current_strips(context)
        if context.scene.vseqf.ripple_markers:
            markers = context.scene.timeline_markers
        else:
            markers = []
        grabs.ripple_timeline(context.scene.sequence_editor, strips, cut_frame - 1, insert, markers=markers)

    def start_cut(self, context, cut_frame, side="BOTH"):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            return{'CANCELLED'}
        #bpy.ops.ed.undo_push()
        if self.use_all:
            cut_all = self.all
        else:
            cut_all = context.scene.vseqf.quickcuts_all

        #Uncuts
        if self.type == 'UNCUT':
            return self.uncut(context, side=side)
        if self.type == 'UNCUT_LEFT':
            return self.uncut(context, side='LEFT')
        if self.type == 'UNCUT_RIGHT':
            return self.uncut(context, side='RIGHT')

        #Insert only
        if self.type == 'INSERT_ONLY':
            self.do_insert(context, cut_frame)
            return{'FINISHED'}

        #Basic cuts
        if self.type in ['HARD', 'SOFT', 'INSERT']:
            if self.type == 'INSERT':
                cut_type = 'SOFT'
            else:
                cut_type = self.type
            if cut_all:
                old_selected = timeline.current_selected(context)
                bpy.ops.sequencer.select_all()
            bpy.ops.sequencer.split(frame=cut_frame, side=side, type=cut_type)
            if cut_all:
                bpy.ops.sequencer.select_all(action='DESELECT')
                for strip in old_selected:
                    strip.select = True
            if self.type == 'INSERT':
                self.do_insert(context, cut_frame)
            return{'FINISHED'}

        #trims, slides and ripples
        if self.type in ['TRIM', 'SLIDE', 'RIPPLE'] and side == 'BOTH':
            return{'CANCELLED'}
        if self.type in ['TRIM_LEFT', 'TRIM_RIGHT', 'SLIDE_LEFT', 'SLIDE_RIGHT', 'RIPPLE_LEFT', 'RIPPLE_RIGHT']:
            action, side = self.type.split('_')
        else:
            action = self.type

        strips = timeline.current_strips(context)

        #determine all strips available to cut
        to_cut = []
        to_cut_temp = []
        for strip in strips:
            if not timeline.is_locked(sequencer, strip) and timeline.under_cursor(strip, cut_frame) and not hasattr(strip, 'input_1'):
                if self.all:
                    to_cut.append(strip)
                    to_cut_temp.append(strip)
                elif strip.select:
                    to_cut.append(strip)
                    to_cut_temp.append(strip)

        #find the ripple amount
        ripple_amount = 0
        for strip in to_cut_temp:
            if side == 'LEFT':
                cut_amount = cut_frame - strip.frame_final_start
            else:
                cut_amount = strip.frame_final_end - cut_frame
            if cut_amount > ripple_amount:
                ripple_amount = cut_amount

        #perform adjustments
        to_cut.sort(key=lambda x: x.frame_final_start)
        for strip in to_cut:
            cutable = timeline.under_cursor(strip, cut_frame)
            if side == 'LEFT':
                if cutable:
                    strip.frame_final_start = cut_frame
                if action == 'SLIDE':
                    strip.frame_start = strip.frame_start - ripple_amount
            else:
                if cutable:
                    strip.frame_final_end = cut_frame
                if action == 'SLIDE':
                    strip.frame_start = strip.frame_start + ripple_amount

        #ripple
        if action == 'RIPPLE':
            if side == 'LEFT':
                ripple_frame = cut_frame - ripple_amount
            else:
                ripple_frame = cut_frame
            insert = 0 - ripple_amount
            if context.scene.vseqf.ripple_markers:
                markers = context.scene.timeline_markers
            else:
                markers = []
            grabs.ripple_timeline(sequencer, strips, ripple_frame - 1, insert, markers=markers)

        if side == 'LEFT':
            if action in ['RIPPLE', 'SLIDE']:
                context.scene.frame_current = context.scene.frame_current - ripple_amount
        else:
            if action in ['SLIDE']:
                context.scene.frame_current = context.scene.frame_current + ripple_amount
        return{'FINISHED'}


class VSEQFQuickCutsMenu(bpy.types.Menu):
    """Popup Menu for QuickCuts operators and properties"""

    bl_idname = "VSEQF_MT_quickcuts_menu"
    bl_label = "Quick Cuts"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not context.strips or not context.scene.sequence_editor:
            return False
        if len(context.strips) > 0:
            return prefs.cuts
        else:
            return False

    def draw(self, context):
        quickcuts_all = context.scene.vseqf.quickcuts_all
        if quickcuts_all:
            cut_strips = 'all'
        else:
            cut_strips = 'selected'
        layout = self.layout
        props = layout.operator('vseqf.cut', text='Cut')
        props.type = 'SOFT'
        props.tooltip = 'Cut '+cut_strips+' strips under the cursor'
        props = layout.operator('vseqf.cut', text='Cut Insert')
        props.type = 'INSERT'
        props.tooltip = 'Cut '+cut_strips+' strips under the cursor and insert '+str(context.scene.vseqf.quickcuts_insert)+' frames'
        props = layout.operator('vseqf.delete', text='Delete', icon='X')
        props.tooltip = 'Delete selected strips'
        props = layout.operator('vseqf.delete', text='Ripple Delete', icon='X')
        props.ripple = True
        props.tooltip = 'Delete selected strips, and slide following strips back to close the gap'
        layout.separator()
        props = layout.operator('vseqf.cut', text='Trim Left')
        props.type = 'TRIM_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' strips under the cursor'
        props = layout.operator('vseqf.cut', text='Slide Trim Left', icon='BACK')
        props.type = 'SLIDE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' strips under the cursor, and slide cut strips back to close the gap'
        props = layout.operator('vseqf.cut', text='Ripple Trim Left', icon='BACK')
        props.type = 'RIPPLE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' strips under the cursor, and slide all strips back to close the gap'
        props = layout.operator('vseqf.cut', text='UnCut Left', icon='LOOP_BACK')
        props.type = 'UNCUT_LEFT'
        props.tooltip = 'Merge selected strips to those on left if they match source and position'
        layout.separator()
        props = layout.operator('vseqf.cut', text='Trim Right')
        props.type = 'TRIM_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' strips under the cursor'
        props = layout.operator('vseqf.cut', text='Slide Trim Right', icon='FORWARD')
        props.type = 'SLIDE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' strips under the cursor, and slide cut strips forward to close the gap'
        props = layout.operator('vseqf.cut', text='Ripple Trim Right', icon='FORWARD')
        props.type = 'RIPPLE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' strips under the cursor, and slide all strips back to close the gap'
        props = layout.operator('vseqf.cut', text='UnCut Right', icon='LOOP_FORWARDS')
        props.type = 'UNCUT_RIGHT'
        props.tooltip = 'Merge selected strips to those on right if they match source and position'
        layout.separator()
        layout.prop(context.scene.vseqf, 'quickcuts_all', toggle=True)
        layout.prop(context.scene.vseqf, 'quickcuts_insert')
        layout.menu("VSEQF_MT_quicktimeline_menu")


class VSEQF_PT_QuickCutsPanel(bpy.types.Panel):
    """Panel for QuickCuts operators and properties"""

    bl_label = "Quick Cuts"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Sequencer"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not context.strips or not context.scene.sequence_editor:
            return False
        if len(context.strips) > 0:
            return prefs.cuts
        else:
            return False

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        quickcuts_all = context.scene.vseqf.quickcuts_all
        if quickcuts_all:
            cut_strips = 'all'
        else:
            cut_strips = 'selected'
        row.prop(context.scene.vseqf, 'quickcuts_all', toggle=True)
        row.prop(context.scene.vseqf, 'quickcuts_insert')
        box = layout.box()
        row = box.row()
        props = row.operator('vseqf.cut', text='Cut')
        props.type = 'SOFT'
        props.tooltip = 'Cut '+cut_strips+' strips under the cursor'
        props = row.operator('vseqf.cut', text='Cut Insert')
        props.type = 'INSERT'
        props.tooltip = 'Cut '+cut_strips+' strips under the cursor and insert '+str(context.scene.vseqf.quickcuts_insert)+' frames'

        row = box.row()
        props = row.operator('vseqf.delete', text='Delete', icon='X')
        props.tooltip = 'Delete selected strips'
        props = row.operator('vseqf.delete', text='Ripple Delete', icon='X')
        props.ripple = True
        props.tooltip = 'Delete selected strips, and slide following strips back to close the gap'

        box = layout.box()
        row = box.row()
        split = row.split(factor=.5, align=True)
        column = split.column(align=True)
        props = column.operator('vseqf.cut', text='Trim Left', icon='BACK')
        props.type = 'TRIM_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' strips under the cursor'
        props = column.operator('vseqf.cut', text='Slide Trim Left', icon='BACK')
        props.type = 'SLIDE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' strips under the cursor, and slide cut strips back to close the gap'
        props = column.operator('vseqf.cut', text='Ripple Trim Left', icon='BACK')
        props.type = 'RIPPLE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' strips under the cursor, and slide all sequences back to close the gap'
        props = column.operator('vseqf.cut', text='UnCut Left', icon='LOOP_BACK')
        props.type = 'UNCUT_LEFT'
        props.tooltip = 'Merge selected strips to those on left if they match source and position'

        column = split.column(align=True)
        props = column.operator('vseqf.cut', text='Trim Right', icon='FORWARD')
        props.type = 'TRIM_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' strips under the cursor'
        props = column.operator('vseqf.cut', text='Slide Trim Right', icon='FORWARD')
        props.type = 'SLIDE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' strips under the cursor, and slide cut strips forward to close the gap'
        props = column.operator('vseqf.cut', text='Ripple Trim Right', icon='FORWARD')
        props.type = 'RIPPLE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' strips under the cursor, and slide all strips back to close the gap'
        props = column.operator('vseqf.cut', text='UnCut Right', icon='LOOP_FORWARDS')
        props.type = 'UNCUT_RIGHT'
        props.tooltip = 'Merge selected strips to those on right if they match source and position'


class VSEQFDelete(bpy.types.Operator):
    """Operator to perform sequencer delete operations, while handling rippling."""

    bl_idname = 'vseqf.delete'
    bl_label = 'VSEQF Delete'

    ripple: bpy.props.BoolProperty(default=False)
    tooltip: bpy.props.StringProperty("Delete the selected strips")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def reset(self):
        self.ripple = False

    def execute(self, context):
        bpy.ops.ed.undo_push()
        to_delete = timeline.current_selected(context)
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
        bpy.ops.sequencer.delete()

        if self.ripple:
            #Ripple remaining strips
            strips = timeline.current_strips(context)
            ripple_frames = list(ripple_frames)
            ripple_frames.sort()
            start_frame = ripple_frames[0]
            end_frame = ripple_frames[0]
            ripple_frames.append(ripple_frames[-1]+2)
            for frame in ripple_frames:
                if frame - end_frame > 1:
                    #Ripple section, start next section
                    ripple_length = end_frame - start_frame
                    if context.scene.vseqf.ripple_markers:
                        markers = context.scene.timeline_markers
                    else:
                        markers = []
                    grabs.ripple_timeline(context.scene.sequence_editor, strips, start_frame, -ripple_length, markers=markers)
                    start_frame = frame
                end_frame = frame
            context.scene.frame_current = ripple_frames[0]
        self.reset()
        return {'FINISHED'}


class VSEQFDeleteConfirm(bpy.types.Operator):
    """Operator to call the delete menu if it's setting is activated"""

    bl_idname = 'vseqf.delete_confirm'
    bl_label = 'VSEQF Delete'

    @classmethod
    def poll(cls, context):
        return not context.scene.sequence_editor.selected_retiming_keys

    def execute(self, context):
        if context.scene.vseqf.delete_confirm:
            bpy.ops.wm.call_menu(name='VSEQF_MT_delete_menu')
        else:
            bpy.ops.vseqf.delete()
        return {'FINISHED'}


class VSEQFDeleteConfirmMenu(bpy.types.Menu):
    bl_idname = "VSEQF_MT_delete_menu"
    bl_label = "Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete')


class VSEQFDeleteRippleConfirm(bpy.types.Operator):
    """Operator to call the ripple delete menu if it's setting is activated"""

    bl_idname = 'vseqf.delete_ripple_confirm'
    bl_label = 'VSEQF Ripple Delete'

    @classmethod
    def poll(cls, context):
        return not context.scene.sequence_editor.selected_retiming_keys

    def execute(self, context):
        if context.scene.vseqf.delete_confirm:
            bpy.ops.wm.call_menu(name='VSEQF_MT_delete_ripple_menu')
        else:
            bpy.ops.vseqf.delete(ripple=True)
        return {'FINISHED'}


class VSEQFDeleteRippleConfirmMenu(bpy.types.Menu):
    bl_idname = "VSEQF_MT_delete_ripple_menu"
    bl_label = "Ripple Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete').ripple = True
