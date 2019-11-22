import bpy
from . import vseqf


class VSEQF_PT_QuickMarkersPanel(bpy.types.Panel):
    """Panel for QuickMarkers operators and properties"""
    bl_label = "Quick Markers"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Sequencer"

    @classmethod
    def poll(cls, context):
        del context
        prefs = vseqf.get_prefs()
        return prefs.markers

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        row = layout.row()
        split = row.split(factor=.9, align=True)
        split.prop(scene.vseqf, 'current_marker')
        split.operator('vseqf.quickmarkers_add_preset', text="", icon="PLUS").preset = scene.vseqf.current_marker
        row = layout.row()
        row.template_list("VSEQF_UL_QuickMarkerPresetList", "", scene.vseqf, 'marker_presets', scene.vseqf, 'marker_index', rows=2)
        row = layout.row()
        row.prop(scene.vseqf, 'marker_deselect', toggle=True)
        row = layout.row()
        row.label(text="Marker List:")
        row = layout.row()
        row.template_list("VSEQF_UL_QuickMarkerList", "", scene, "timeline_markers", scene.vseqf, "marker_index", rows=4)


class VSEQF_UL_QuickMarkerPresetList(bpy.types.UIList):
    """Draws an editable list of QuickMarker presets"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        split = layout.split(factor=.9, align=True)
        split.operator('vseqf.quickmarkers_place', text=item.text).marker = item.text
        split.operator('vseqf.quickmarkers_remove_preset', text='', icon='X').marker = item.text

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, property):
        del context
        markers = getattr(data, property)
        helper = bpy.types.UI_UL_list
        flt_neworder = helper.sort_items_by_name(markers, 'text')
        return [], flt_neworder


class VSEQF_UL_QuickMarkerList(bpy.types.UIList):
    """Draws an editable list of current markers in the timeline"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del data, icon, active_data, active_propname
        timecode = vseqf.timecode_from_frames(item.frame, vseqf.get_fps(context.scene), levels=0, subsecond_type='frames')
        split = layout.split(factor=.9, align=True)
        subsplit = split.split(align=True)
        subsplit.operator('vseqf.quickmarkers_jump', text=item.name+' ('+timecode+')').frame = item.frame
        if item.frame == context.scene.frame_current:
            subsplit.enabled = False
        split.operator('vseqf.quickmarkers_delete', text='', icon='X').frame = item.frame

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, property):
        del context
        markers = getattr(data, property)
        helper = bpy.types.UI_UL_list
        flt_neworder = helper.sort_items_helper(list(enumerate(markers)), key=lambda x: x[1].frame)
        return [], flt_neworder


class VSEQFQuickMarkerDelete(bpy.types.Operator):
    """Operator to delete a marker on a given frame
    If no marker is on the frame, nothing will be done

    Argument:
        frame: Integer, the frame to delete a marker from"""

    bl_idname = 'vseqf.quickmarkers_delete'
    bl_label = 'Delete Marker At Frame'

    frame: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        markers = scene.timeline_markers
        for marker in markers:
            if marker.frame == self.frame:
                bpy.ops.ed.undo_push()
                markers.remove(marker)
                break
        return{'FINISHED'}


class VSEQFQuickMarkerMove(bpy.types.Operator):
    bl_idname = 'vseqf.quickmarkers_move'
    bl_label = 'Move This Marker'

    frame: bpy.props.IntProperty()

    def execute(self, context):
        marker = None
        for timeline_marker in context.scene.timeline_markers:
            if timeline_marker.frame == self.frame:
                marker = timeline_marker
                timeline_marker.select = True
            else:
                timeline_marker.select = False
        if marker:
            bpy.ops.marker.move('INVOKE_DEFAULT')
        return {'FINISHED'}


class VSEQFQuickMarkerRename(bpy.types.Operator):
    bl_idname = 'vseqf.quickmarkers_rename'
    bl_label = 'Rename This Marker'

    marker_name: bpy.props.StringProperty(name='Marker Name')

    def execute(self, context):
        for marker in context.scene.timeline_markers:
            if marker.frame == context.scene.vseqf.current_marker_frame:
                marker.name = self.marker_name
        return{'FINISHED'}

    def invoke(self, context, event):
        del event
        for marker in context.scene.timeline_markers:
            if marker.frame == context.scene.vseqf.current_marker_frame:
                self.marker_name = marker.name
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class VSEQFQuickMarkerJump(bpy.types.Operator):
    """Operator to move the cursor to a given frame
    Note that a marker doesn't have to be at the frame, that is just the way the script uses this.

    Argument:
        frame: Integer, the frame number to jump to"""
    bl_idname = 'vseqf.quickmarkers_jump'
    bl_label = 'Jump To Timeline Marker'

    frame: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        scene.frame_current = self.frame
        return{'FINISHED'}


class VSEQFQuickMarkersMenu(bpy.types.Menu):
    """Menu for adding QuickMarkers to the current frame of the timeline"""
    bl_idname = "VSEQF_MT_quickmarkers_menu"
    bl_label = "Add Marker"

    @classmethod
    def poll(cls, context):
        del context
        prefs = vseqf.get_prefs()
        return prefs.markers

    def draw(self, context):
        del context
        scene = bpy.context.scene
        layout = self.layout
        if len(scene.vseqf.marker_presets) == 0:
            layout.label(text='No Marker Presets')
        else:
            for marker in scene.vseqf.marker_presets:
                layout.operator('vseqf.quickmarkers_place', text=marker.text).marker = marker.text


class VSEQFQuickMarkersPlace(bpy.types.Operator):
    """Adds a marker with a specific name to the current frame of the timeline
    If a marker already exists at the current frame, it will be renamed

    Argument:
        marker: String, the name of the marker to place"""

    bl_idname = 'vseqf.quickmarkers_place'
    bl_label = 'VSEQF Quick Markers Place A Marker'

    marker: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        exists = False
        for marker in scene.timeline_markers:
            if marker.frame == frame:
                bpy.ops.ed.undo_push()
                marker.name = self.marker
                if scene.vseqf.marker_deselect:
                    marker.select = False
                exists = True
        if not exists:
            bpy.ops.ed.undo_push()
            marker = scene.timeline_markers.new(name=self.marker, frame=frame)
            if scene.vseqf.marker_deselect:
                marker.select = False
        return{'FINISHED'}


class VSEQFQuickMarkersRemovePreset(bpy.types.Operator):
    """Removes a marker name preset from the QuickMarkers preset list

    Argument:
        marker: String, the name of the marker preset to be removed"""

    bl_idname = 'vseqf.quickmarkers_remove_preset'
    bl_label = 'VSEQF Quick Markers Remove Preset'

    #marker name to be removed
    marker: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        for index, marker_preset in reversed(list(enumerate(scene.vseqf.marker_presets))):
            if marker_preset.text == self.marker:
                bpy.ops.ed.undo_push()
                scene.vseqf.marker_presets.remove(index)
        return{'FINISHED'}


class VSEQFQuickMarkersAddPreset(bpy.types.Operator):
    """Adds a name preset to QuickMarkers presets
    If the name already exists in the presets, the operator is canceled

    Argument:
        preset: String, the name of the marker preset to add"""

    bl_idname = 'vseqf.quickmarkers_add_preset'
    bl_label = 'VSEQF Quick Markers Add Preset'

    preset: bpy.props.StringProperty()

    def execute(self, context):
        if not self.preset:
            return {'CANCELLED'}
        scene = context.scene
        for marker_preset in scene.vseqf.marker_presets:
            if marker_preset.text == self.preset:
                return {'CANCELLED'}
        bpy.ops.ed.undo_push()
        preset = scene.vseqf.marker_presets.add()
        preset.text = self.preset
        return {'FINISHED'}


class VSEQFMarkerPreset(bpy.types.PropertyGroup):
    """Property for marker presets"""
    text: bpy.props.StringProperty(name="Text", default="")
