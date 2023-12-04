import bpy
from . import parenting
from . import timeline
from . import grabs
from . import vseqf


def vseqf_cut(sequence, frame=0, cut_type="SOFT"):
    #Check parenting settings, remove if parent strip doesnt exist (prevents cut strips from getting false parents)
    parent = parenting.find_parent(sequence)
    if not parent:
        sequence.parent = ''

    bpy.ops.sequencer.select_all(action='DESELECT')
    left_sequence = False
    right_sequence = False
    if frame > sequence.frame_final_start and frame < sequence.frame_final_end:
        sequence.select = True
        try:
            bpy.ops.sequencer.split(frame=frame, type=cut_type, side="BOTH")  #Changed in 2.83
        except AttributeError:
            bpy.ops.sequencer.cut(frame=frame, type=cut_type, side="BOTH")
        sequences = timeline.current_selected(bpy.context)
        for seq in sequences:
            seq.select = False
            if seq.frame_final_start < frame:
                left_sequence = seq
            else:
                right_sequence = seq
    else:
        if sequence.frame_final_end <= frame:
            left_sequence = sequence
        else:
            right_sequence = sequence
    return left_sequence, right_sequence


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
    bl_label = "Wrapper for the built in sequence cut operator that maintains parenting relationships and provides extra cut operations."
    bl_options = {"UNDO"}

    tooltip: bpy.props.StringProperty("Cut the selected strips")
    use_frame: bpy.props.BoolProperty(default=False)
    frame = bpy.props.IntProperty(0)
    type: bpy.props.EnumProperty(name='Type', items=[("SOFT", "Soft", "", 1), ("HARD", "Hard", "", 2), ("INSERT", "Insert Cut", "", 3), ("INSERT_ONLY", "Insert Only", "", 4), ("TRIM", "Trim", "", 5), ("TRIM_LEFT", "Trim Left", "", 6), ("TRIM_RIGHT", "Trim Right", "", 7), ("SLIDE", "Slide", "", 8), ("SLIDE_LEFT", "Slide Left", "", 9), ("SLIDE_RIGHT", "Slide Right", "", 10), ("RIPPLE", "Ripple", "", 11), ("RIPPLE_LEFT", "Ripple Left", "", 12), ("RIPPLE_RIGHT", "Ripple Right", "", 13), ("UNCUT", "UnCut", "", 14), ("UNCUT_LEFT", "UnCut Left", "", 15), ("UNCUT_RIGHT", "UnCut Right", "", 16)], default='SOFT')
    side: bpy.props.EnumProperty(name='Side', items=[("BOTH", "Both", "", 1), ("RIGHT", "Right", "", 2), ("LEFT", "Left", "", 3)], default='BOTH')
    all: bpy.props.BoolProperty(name='Cut All', default=False)
    use_all: bpy.props.BoolProperty(default=False)
    insert: bpy.props.IntProperty(0)
    use_insert: bpy.props.BoolProperty(default=False)

    def __init__(self):
        if not self.use_frame:
            self.frame = bpy.context.scene.frame_current

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

    def delete_sequence(self, sequence):
        """Deletes a sequence while maintaining previous selected and active sequences
        Argument:
            sequence: VSE Sequence object to delete"""

        active = timeline.current_active(bpy.context)
        selected = []
        for seq in bpy.context.scene.sequence_editor.sequences:
            if seq.select:
                selected.append(seq)
                seq.select = False
        sequence.select = True
        bpy.ops.sequencer.delete()
        for seq in selected:
            seq.select = True
        if active:
            bpy.context.scene.sequence_editor.active_strip = active

    def check_source(self, sequence, next_sequence):
        """Used by UnCut, checks the source and position of two sequences to see if they can be merged

        Arguments:
            sequence: VSE Sequence object to be compared
            next_sequence: VSE Sequence object to be compared

        Returns: Boolean"""

        if sequence.type == next_sequence.type:
            if sequence.type == 'IMAGE':
                if sequence.directory == next_sequence.directory and sequence.elements[0].filename == next_sequence.elements[0].filename:
                    if len(sequence.elements) == 1 and len(next_sequence.elements) == 1:
                        return True
                    elif sequence.frame_start == next_sequence.frame_start:
                        return True
            elif sequence.frame_start == next_sequence.frame_start:
                if sequence.type == 'SOUND':
                    if sequence.sound.filepath == next_sequence.sound.filepath:
                        return True
                if sequence.type == 'MOVIE':
                    if sequence.filepath == next_sequence.filepath:
                        return True
                if sequence.type == 'SCENE':
                    if sequence.scene == next_sequence.scene:
                        return True
                if sequence.type == 'MOVIECLIP':

                    #no way of checking source file :\
                    pass
        return False

    def execute(self, context):
        return self.start_cut(context)

    def invoke(self, context, event):
        mouse_x = event.mouse_region_x
        cut_frame = self.frame
        region = context.region
        view = region.view2d
        cursor, bottom = view.view_to_region(cut_frame, 0, clip=False)
        if mouse_x < cursor:
            side = 'LEFT'
        else:
            side = 'RIGHT'
        return self.start_cut(context, side)

    def uncut(self, context, side="BOTH"):
        #merges a sequence to the one on the left or right if they share the same source and position
        if side == 'BOTH':
            self.reset()
            return{"CANCELLED"}

        sequencer = context.scene.sequence_editor
        selected = timeline.current_selected(context)
        to_uncut = []
        for sequence in selected:
            if not timeline.is_locked(sequencer, sequence) and not hasattr(sequence, 'input_1'):
                to_uncut.append(sequence)
        for sequence in to_uncut:
            if side == 'LEFT':
                direction = 'previous'
            else:
                direction = 'next'
            sequences = timeline.current_sequences(context)
            merge_to = timeline.find_close_sequence(sequences, sequence, direction=direction, mode='channel', sounds=True)
            if merge_to:
                if not timeline.is_locked(sequencer, merge_to):
                    source_matches = self.check_source(sequence, merge_to)
                    if source_matches:
                        merge_to_children = parenting.find_children(merge_to)
                        parenting.add_children(sequence, merge_to_children)
                        parenting.clear_children(merge_to)
                        if direction == 'next':
                            newend = merge_to.frame_final_end
                            self.delete_sequence(merge_to)
                            sequence.frame_final_end = newend
                        else:
                            newstart = merge_to.frame_final_start
                            self.delete_sequence(merge_to)
                            sequence.frame_final_start = newstart
        self.reset()
        return{'FINISHED'}

    def start_cut(self, context, side="BOTH"):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            self.reset()
            return{'CANCELLED'}
        #bpy.ops.ed.undo_push()
        if not self.use_all:
            self.all = context.scene.vseqf.quickcuts_all
        if self.type == 'UNCUT_LEFT':
            return self.uncut(context, side='LEFT')
        if self.type == 'UNCUT_RIGHT':
            return self.uncut(context, side='RIGHT')
        if self.type == 'TRIM_LEFT':
            self.type = 'TRIM'
            side = 'LEFT'
        if self.type == 'TRIM_RIGHT':
            self.type = 'TRIM'
            side = 'RIGHT'
        if self.type == 'SLIDE_LEFT':
            self.type = 'SLIDE'
            side = 'LEFT'
        if self.type == 'SLIDE_RIGHT':
            self.type = 'SLIDE'
            side = 'RIGHT'
        if self.type == 'RIPPLE_LEFT':
            self.type = 'RIPPLE'
            side = 'LEFT'
        if self.type == 'RIPPLE_RIGHT':
            self.type = 'RIPPLE'
            side = 'RIGHT'
        sequences = timeline.current_sequences(context)
        active = timeline.current_active(context)
        to_cut = []
        to_select = []
        to_active = None
        cut_pairs = []

        #determine all sequences available to cut
        to_cut_temp = []
        for sequence in sequences:
            if not timeline.is_locked(sequencer, sequence) and timeline.under_cursor(sequence, self.frame) and not hasattr(sequence, 'input_1'):
                if self.all:
                    to_cut.append(sequence)
                    to_cut_temp.append(sequence)
                elif sequence.select:
                    to_cut.append(sequence)
                    to_cut_temp.append(sequence)
                    if vseqf.parenting():
                        children = parenting.get_recursive(sequence, [])
                        for child in children:
                            if not timeline.is_locked(sequencer, child) and (not hasattr(child, 'input_1')) and child not in to_cut:
                                to_cut.append(child)

        #find the ripple amount
        ripple_amount = 0
        for sequence in to_cut_temp:
            if side == 'LEFT':
                cut_amount = self.frame - sequence.frame_final_start
            else:
                cut_amount = sequence.frame_final_end - self.frame
            #to_cut.append(sequence)
            if cut_amount > ripple_amount:
                ripple_amount = cut_amount

        if side == 'LEFT':
            ripple_frame = self.frame - ripple_amount
        else:
            ripple_frame = self.frame

        bpy.ops.sequencer.select_all(action='DESELECT')
        to_cut.sort(key=lambda x: x.frame_final_start)
        for sequence in to_cut:
            cutable = timeline.under_cursor(sequence, self.frame)
            left = False
            right = False
            if self.type in ['TRIM', 'SLIDE', 'RIPPLE']:
                if side != 'BOTH':
                    if side == 'LEFT':
                        if cutable:
                            sequence.frame_final_start = self.frame
                        to_select.append(sequence)
                        if self.type == 'SLIDE':
                            sequence.frame_start = sequence.frame_start - ripple_amount
                    else:
                        if cutable:
                            sequence.frame_final_end = self.frame
                        to_select.append(sequence)
                        if self.type == 'SLIDE':
                            sequence.frame_start = sequence.frame_start + ripple_amount
                else:
                    ripple_amount = 0

            if self.type in ['SOFT', 'HARD', 'INSERT']:
                if self.type == 'INSERT':
                    cut_type = 'SOFT'
                else:
                    cut_type = self.type
                if cutable:
                    left, right = vseqf_cut(sequence=sequence, frame=self.frame, cut_type=cut_type)
                    cut_pairs.append([left, right])
            else:
                to_select.append(sequence)
            if (side == 'LEFT' or side == 'BOTH') and left:
                to_select.append(left)
                if active and left == active:
                    to_active = left
            if (side == 'RIGHT' or side == 'BOTH') and right:
                to_select.append(right)
                if active and left == active and side != 'BOTH':
                    to_active = right
        timeline.fix_effects(cut_pairs, sequences)
        #fix parenting of cut sequences
        for cut_pair in cut_pairs:
            left, right = cut_pair
            if right and left:
                children = parenting.find_children(left)
                for child in children:
                    if child.frame_final_start >= right.frame_final_start:
                        child.parent = right.name

        #ripple/insert
        if self.type == 'INSERT' or self.type == 'RIPPLE' or self.type == 'INSERT_ONLY':
            if self.type == 'RIPPLE':
                insert = 0 - ripple_amount
            else:
                if self.use_insert:
                    insert = self.insert
                else:
                    insert = context.scene.vseqf.quickcuts_insert
            sequences = timeline.current_sequences(context)
            if context.scene.vseqf.ripple_markers:
                markers = context.scene.timeline_markers
            else:
                markers = []
            grabs.ripple_timeline(sequencer, sequences, ripple_frame - 1, insert, markers=markers)
        else:
            for sequence in to_select:
                if sequence:
                    sequence.select = True
        if to_active:
            context.scene.sequence_editor.active_strip = to_active
        if side == 'LEFT':
            if self.type in ['RIPPLE', 'SLIDE']:
                context.scene.frame_current = context.scene.frame_current - ripple_amount
        else:
            if self.type in ['SLIDE']:
                context.scene.frame_current = context.scene.frame_current + ripple_amount
        self.reset()
        return{'FINISHED'}


class VSEQFQuickCutsMenu(bpy.types.Menu):
    """Popup Menu for QuickCuts operators and properties"""

    bl_idname = "VSEQF_MT_quickcuts_menu"
    bl_label = "Quick Cuts"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not context.sequences or not context.scene.sequence_editor:
            return False
        if len(context.sequences) > 0:
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
        props.tooltip = 'Cut '+cut_strips+' sequences under the cursor'
        props = layout.operator('vseqf.cut', text='Cut Insert')
        props.type = 'INSERT'
        props.tooltip = 'Cut '+cut_strips+' sequences under the cursor and insert '+str(context.scene.vseqf.quickcuts_insert)+' frames'
        props = layout.operator('vseqf.delete', text='Delete', icon='X')
        props.tooltip = 'Delete selected sequences'
        props = layout.operator('vseqf.delete', text='Ripple Delete', icon='X')
        props.ripple = True
        props.tooltip = 'Delete selected sequences, and slide following sequences back to close the gap'
        layout.separator()
        props = layout.operator('vseqf.cut', text='Trim Left')
        props.type = 'TRIM_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' sequences under the cursor'
        props = layout.operator('vseqf.cut', text='Slide Trim Left', icon='BACK')
        props.type = 'SLIDE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' sequences under the cursor, and slide cut sequences back to close the gap'
        props = layout.operator('vseqf.cut', text='Ripple Trim Left', icon='BACK')
        props.type = 'RIPPLE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' sequences under the cursor, and slide all sequences back to close the gap'
        props = layout.operator('vseqf.cut', text='UnCut Left', icon='LOOP_BACK')
        props.type = 'UNCUT_LEFT'
        props.tooltip = 'Merge selected sequences to those on left if they match source and position'
        layout.separator()
        props = layout.operator('vseqf.cut', text='Trim Right')
        props.type = 'TRIM_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' sequences under the cursor'
        props = layout.operator('vseqf.cut', text='Slide Trim Right', icon='FORWARD')
        props.type = 'SLIDE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' sequences under the cursor, and slide cut sequences forward to close the gap'
        props = layout.operator('vseqf.cut', text='Ripple Trim Right', icon='FORWARD')
        props.type = 'RIPPLE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' sequences under the cursor, and slide all sequences back to close the gap'
        props = layout.operator('vseqf.cut', text='UnCut Right', icon='LOOP_FORWARDS')
        props.type = 'UNCUT_RIGHT'
        props.tooltip = 'Merge selected sequences to those on right if they match source and position'
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

        if not context.sequences or not context.scene.sequence_editor:
            return False
        if len(context.sequences) > 0:
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
        props.tooltip = 'Cut '+cut_strips+' sequences under the cursor'
        props = row.operator('vseqf.cut', text='Cut Insert')
        props.type = 'INSERT'
        props.tooltip = 'Cut '+cut_strips+' sequences under the cursor and insert '+str(context.scene.vseqf.quickcuts_insert)+' frames'

        row = box.row()
        props = row.operator('vseqf.delete', text='Delete', icon='X')
        props.tooltip = 'Delete selected sequences'
        props = row.operator('vseqf.delete', text='Ripple Delete', icon='X')
        props.ripple = True
        props.tooltip = 'Delete selected sequences, and slide following sequences back to close the gap'

        box = layout.box()
        row = box.row()
        split = row.split(factor=.5, align=True)
        column = split.column(align=True)
        props = column.operator('vseqf.cut', text='Trim Left', icon='BACK')
        props.type = 'TRIM_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' sequences under the cursor'
        props = column.operator('vseqf.cut', text='Slide Trim Left', icon='BACK')
        props.type = 'SLIDE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' sequences under the cursor, and slide cut sequences back to close the gap'
        props = column.operator('vseqf.cut', text='Ripple Trim Left', icon='BACK')
        props.type = 'RIPPLE_LEFT'
        props.tooltip = 'Cut off the left side of '+cut_strips+' sequences under the cursor, and slide all sequences back to close the gap'
        props = column.operator('vseqf.cut', text='UnCut Left', icon='LOOP_BACK')
        props.type = 'UNCUT_LEFT'
        props.tooltip = 'Merge selected sequences to those on left if they match source and position'

        column = split.column(align=True)
        props = column.operator('vseqf.cut', text='Trim Right', icon='FORWARD')
        props.type = 'TRIM_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' sequences under the cursor'
        props = column.operator('vseqf.cut', text='Slide Trim Right', icon='FORWARD')
        props.type = 'SLIDE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' sequences under the cursor, and slide cut sequences forward to close the gap'
        props = column.operator('vseqf.cut', text='Ripple Trim Right', icon='FORWARD')
        props.type = 'RIPPLE_RIGHT'
        props.tooltip = 'Cut off the right side of '+cut_strips+' sequences under the cursor, and slide all sequences back to close the gap'
        props = column.operator('vseqf.cut', text='UnCut Right', icon='LOOP_FORWARDS')
        props.type = 'UNCUT_RIGHT'
        props.tooltip = 'Merge selected sequences to those on right if they match source and position'


class VSEQFDelete(bpy.types.Operator):
    """Operator to perform sequencer delete operations, while handling parents and rippling."""

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
        for sequence in to_delete:
            if vseqf.parenting() and context.scene.vseqf.delete_children:
                children = parenting.find_children(sequence)
                for child in children:
                    if child not in to_delete:
                        child.select = True
        bpy.ops.sequencer.delete()

        if self.ripple:
            #Ripple remaining sequences
            sequences = timeline.current_sequences(context)
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
                    grabs.ripple_timeline(context.scene.sequence_editor, sequences, start_frame, -ripple_length, markers=markers)
                    start_frame = frame
                end_frame = frame
            context.scene.frame_current = ripple_frames[0]
        self.reset()
        return {'FINISHED'}


class VSEQFDeleteConfirm(bpy.types.Menu):
    bl_idname = "VSEQF_MT_delete_menu"
    bl_label = "Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete')


class VSEQFDeleteRippleConfirm(bpy.types.Menu):
    bl_idname = "VSEQF_MT_delete_ripple_menu"
    bl_label = "Ripple Delete Selected?"

    def draw(self, context):
        del context
        layout = self.layout
        layout.operator("vseqf.delete", text='Delete').ripple = True
