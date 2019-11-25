import bpy
from . import vseqf
from . import timeline


def get_recursive(sequence, sequences):
    #recursively gathers all children of children of the given sequence
    if not sequence.lock and not hasattr(sequence, 'input_1'):
        if sequence not in sequences:
            sequences.append(sequence)
            children = find_children(sequence)
            for child in children:
                sequences = get_recursive(child, sequences)
    return sequences


def add_children(parent_sequence, child_sequences):
    """Adds parent-child relationships to sequences
    Arguments:
        parent_sequence: VSE Sequence to set as the parent
        child_sequences: List of VSE Sequence objects to set as children"""

    for child_sequence in child_sequences:
        if child_sequence.name != parent_sequence.name:
            child_sequence.parent = parent_sequence.name


def find_children(parent_sequence, name=False, sequences=False):
    """Gets a list of sequences that are children of a sequence
    Arguments:
        parent_sequence: VSE Sequence object or String name of a sequence to search for children of
        name: Boolean, if True, the passed-in 'parent_sequence' is a name of the parent, if False, the passed in 'parent_sequence' is the actual sequence object
        sequences: Optional, a list of sequences may be passed in here, they will be the only ones searched

    Returns: List of VSE Sequence objects, or empty list if none found"""

    if name:
        parent_name = parent_sequence
    else:
        parent_name = parent_sequence.name
    if not sequences:
        sequences = timeline.current_sequences(bpy.context)
    child_sequences = []
    for sequence in sequences:
        if sequence.parent == parent_name:
            child_sequences.append(sequence)
    return child_sequences


def find_parent(child_sequence):
    """Gets the parent sequence of a child sequence
    Argument:
        child_sequence: VSE Sequence object to search for the parent of

    Returns: VSE Sequence object if match found, Boolean False if no match found"""

    if not child_sequence.parent:
        return False
    sequences = timeline.current_sequences(bpy.context)
    for sequence in sequences:
        if sequence.name == child_sequence.parent:
            return sequence
    else:
        return False


def clear_children(parent_sequence):
    """Removes all child relationships from a parent sequence
    Argument:
        parent_sequence: VSE Sequence object to search for children of"""
    scene = bpy.context.scene
    sequences = scene.sequence_editor.sequences_all
    for sequence in sequences:
        if sequence.parent == parent_sequence.name:
            clear_parent(sequence)


def clear_parent(child_sequence):
    """Removes the parent relationship of a child sequence
    Argument:
        child_sequence: VSE Sequence object to remove the parent relationship of"""
    child_sequence.parent = ''


def select_children(parent_sequence, sequences=False):
    """Selects all children of a given sequence
    Arguments:
        parent_sequence: VSE Sequence to search for children of
        sequences: Optional, list of sequences to search through"""

    children = find_children(parent_sequence, sequences=sequences)
    for child in children:
        child.select = True


def select_parent(child_sequence):
    """Selects the parent of a sequence
    Argument:
        child_sequence: VSE Sequence object to find the parent of"""

    parent = find_parent(child_sequence)
    if parent:
        parent.select = True


class VSEQF_PT_Parenting(bpy.types.Panel):
    bl_label = 'Parenting'
    bl_parent_id = "SEQUENCER_PT_adjust"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()
        if prefs.fades:
            active_sequence = timeline.current_active(context)
            if active_sequence:
                return True
        return False

    def draw(self, context):
        #display info about parenting relationships
        sequences = timeline.current_sequences(context)
        active_sequence = timeline.current_active(context)
        layout = self.layout

        children = find_children(active_sequence, sequences=sequences)
        parent = find_parent(active_sequence)

        row = layout.row()
        prop = row.operator('vseqf.quickparents', text='Set Active As Parent')
        prop.action = 'add'
        prop.tooltip = "Set active sequence as the parent of all other selected sequences"

        #List relationships for active sequence
        if parent:
            box = layout.box()
            row = box.row()
            row.label(text="Parent: ")
            row.label(text=parent.name)
            row = box.row()
            prop = row.operator('vseqf.quickparents', text='Select Parent')
            prop.action = 'select_parent'
            prop.tooltip = "Select the parents of all selected sequences"
            prop = row.operator('vseqf.quickparents', text='Remove Parent', icon="X")
            prop.action = 'clear_parent'
            prop.tooltip = "Clear the parents of all selected sequences"
        if len(children) > 0:
            box = layout.box()
            for index, child in enumerate(children):
                row = box.row()
                if index == 0:
                    row.label(text='Children:')
                else:
                    row.label(text='')
                row.label(text=child.name)
            row = box.row()
            prop = row.operator('vseqf.quickparents', text='Select Children')
            prop.action = 'select_children'
            prop.tooltip = "Select children of all selected sequences"
            prop = row.operator('vseqf.quickparents', text='Remove Children', icon="X")
            prop.action = 'clear_children'
            prop.tooltip = "Clear children of all selected sequences"


class VSEQFQuickParentsMenu(bpy.types.Menu):
    """Pop-up menu for QuickParents, displays parenting operators, and relationships"""
    bl_idname = "VSEQF_MT_quickparents_menu"
    bl_label = "Quick Parents"

    @classmethod
    def poll(cls, context):
        del context
        prefs = vseqf.get_prefs()
        return prefs.parenting

    def draw(self, context):
        sequence = timeline.current_active(context)
        layout = self.layout

        if sequence:
            sequences = timeline.current_sequences(context)

            selected = timeline.current_selected(context)
            children = find_children(sequence, sequences=sequences)
            parent = find_parent(sequence)

            prop = layout.operator('vseqf.quickparents', text='Select Children')
            prop.action = 'select_children'
            prop.tooltip = "Select children of all selected sequences"
            prop = layout.operator('vseqf.quickparents', text='Select Parent')
            prop.action = 'select_parent'
            prop.tooltip = "Select the parents of all selected sequences"
            if len(selected) > 1:
                #more than one sequence is selected, so children can be set
                prop = layout.operator('vseqf.quickparents', text='Set Active As Parent')
                prop.action = 'add'
                prop.tooltip = "Set active sequence as the parent of all other selected sequences"

            prop = layout.operator('vseqf.quickparents', text='Clear Children')
            prop.action = 'clear_children'
            prop.tooltip = "Clear children of all selected sequences"
            prop = layout.operator('vseqf.quickparents', text='Clear Parent')
            prop.action = 'clear_parent'
            prop.tooltip = "Clear the parents of all selected sequences"

            if parent:
                #Parent sequence is found, display it
                layout.separator()
                layout.label(text="     Parent: ")
                layout.label(text=parent.name)

            if len(children) > 0:
                #At least one child sequence is found, display them
                layout.separator()
                layout.label(text="     Children:")
                index = 0
                while index < len(children):
                    layout.label(text=children[index].name)
                    index = index + 1

        else:
            layout.label(text='No Sequence Selected')


class VSEQFQuickParents(bpy.types.Operator):
    """Changes parenting relationships on selected sequences

    Argument:
        action: String, determines what this operator will attempt to do
            'add': Adds selected sequences as children of the active sequence
            'select_children': Selects children of all selected sequences
            'select_parent': Selects parents of all selected sequences
            'clear_parent': Clears parent relationships of all selected sequences
            'clear_children': Clears all child relationships of all selected sequences"""

    bl_idname = 'vseqf.quickparents'
    bl_label = 'VSEQF Quick Parents'
    bl_description = 'Sets Or Removes Strip Parents'

    action: bpy.props.StringProperty()
    tooltip: bpy.props.StringProperty("")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):
        selected = timeline.current_selected(context)
        active = timeline.current_active(context)
        if not active:
            return {'CANCELLED'}

        bpy.ops.ed.undo_push()

        if (self.action == 'add') and (len(selected) > 1):
            add_children(active, selected)
        else:
            if not selected:
                selected = [active]
            sequences = timeline.current_sequences(context)
            for sequence in selected:
                if self.action == 'select_children':
                    select_children(sequence, sequences=sequences)
                if self.action == 'select_parent':
                    select_parent(sequence)
                if self.action == 'clear_parent':
                    clear_parent(sequence)
                if self.action == 'clear_children':
                    clear_children(sequence)
        vseqf.redraw_sequencers()
        return {'FINISHED'}


class VSEQFQuickParentsClear(bpy.types.Operator):
    """Clears the parent of a sequence
    Argument:
        strip: String, the name of the sequence to clear the parent of"""

    bl_idname = 'vseqf.quickparents_clear_parent'
    bl_label = 'VSEQF Quick Parent Remove Parent'
    bl_description = 'Removes Strip Parent'

    strip: bpy.props.StringProperty()

    def execute(self, context):
        sequences = timeline.current_sequences(context)
        for sequence in sequences:
            if sequence.name == self.strip:
                bpy.ops.ed.undo_push()
                clear_parent(sequence)
                break
        vseqf.redraw_sequencers()
        return {'FINISHED'}
