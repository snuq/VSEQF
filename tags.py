import bpy
from . import vseqf
from . import timeline


def populate_selected_tags():
    scene = bpy.context.scene
    selected_strips = timeline.current_selected(bpy.context)
    populate_tags(strips=selected_strips, tags=scene.vseqf.selected_tags)


def auto_populate_tags(self, context):
    populate_tags()


def populate_tags(strips=False, tags=False):
    """Iterates through all strips and stores all tags to the 'tags' property group
    If no strips are given, default to all strips in context.
    If no tags group is given, default to scene.vseqf.tags"""

    if strips is False:
        strips = timeline.current_strips(bpy.context)
    if tags is False:
        tags = bpy.context.scene.vseqf.tags

    temp_tags = set()
    for strip in strips:
        for tag in strip.tags:
            temp_tags.add(tag.text)
    try:
        tags.clear()
    except:
        pass
    add_tags = sorted(temp_tags)
    for tag in add_tags:
        new_tag = tags.add()
        new_tag.name = tag


class VSEQFQuickTagsStripMarkerMenu(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_quickmarkers_strip_menu'
    bl_label = 'Strip Markers'

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not context.strips or not context.scene.sequence_editor:
            return False
        if len(context.strips) > 0 and timeline.current_active(context):
            return prefs.tags
        else:
            return False

    def draw(self, context):
        layout = self.layout
        active = timeline.current_active(context)

        #If marker is under cursor, provide rename, position, length and color variables
        marker_tags = []
        for index, tag in enumerate(active.tags):
            if tag.use_offset:
                tag_start = active.frame_start + tag.offset - 1
                tag_end = tag_start + tag.length
                if tag_start <= context.scene.frame_current <= tag_end:
                    marker_tags.append([index, tag])

        split = layout.split()
        column = split.column()

        for tag_data in marker_tags:
            index, tag = tag_data
            column.prop(tag, 'text', text='')
            column.prop(tag, 'offset')
            column.prop(tag, 'length')
            column.label(text="Color:")
            column.separator()

        #Add new marker at cursor position
        column.operator('vseqf.quicktags_add_marker', text="Add Tag At Cursor").text = 'Tag'

        #Add marker of one of the 'All Tags' at current cursor position
        if len(context.scene.vseqf.tags) > 0:
            column.separator()
            for tag in context.scene.vseqf.tags:
                column.operator('vseqf.quicktags_add_marker', text="Add Tag: "+tag.name).text = tag.name

        column = split.column()
        for tag_data in marker_tags:
            index, tag = tag_data
            column.operator('vseqf.quicktags_remove_marker', text='X').index = index
            column.label(text='')
            column.label(text='')
            column.prop(tag, 'color', text='')
            column.separator()

        column.label(text='')
        column.separator()


class VSEQFQuickTagsMenu(bpy.types.Menu):
    bl_idname = 'VSEQF_MT_quicktags_menu'
    bl_label = "Tags"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not context.strips or not context.scene.sequence_editor:
            return False
        if len(context.strips) > 0 and timeline.current_active(context):
            return prefs.tags
        else:
            return False

    def draw(self, context):
        layout = self.layout
        active = timeline.current_active(context)
        if len(active.tags) == 0:
            layout.label(text="No Tags")
        else:
            for tag in active.tags:
                layout.operator('vseqf.quicktags_select', text=tag.text).text = tag.text


class VSEQF_PT_QuickTagsPanel(bpy.types.Panel):
    """Panel for displaying, removing and adding tags"""

    bl_label = "Quick Tags"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not context.strips or not context.scene.sequence_editor:
            return False
        if len(context.strips) > 0 and context.scene.sequence_editor.active_strip:
            return prefs.tags
        else:
            return False

    def draw(self, context):
        scene = context.scene
        strip = timeline.current_active(context)
        selected = timeline.current_selected(context)
        layout = self.layout
        row = layout.row()
        row.label(text='All Tags:')
        row = layout.row()
        row.template_list("VSEQF_UL_QuickTagListAll", "", scene.vseqf, 'tags', scene.vseqf, 'tag_index', rows=3)
        row = layout.row()
        tag_index = scene.vseqf.tag_index
        if len(scene.vseqf.tags) > 0:
            if tag_index >= len(scene.vseqf.tags):
                tag_index = len(scene.vseqf.tags) - 1
            text = scene.vseqf.tags[tag_index].name
            row.operator('vseqf.quicktags_select', text='Select With Tag').text = text
            row = layout.row()
            if len(selected) > 0:
                row.enabled = True
            else:
                row.enabled = False
            row.operator('vseqf.quicktags_add', text='Add Tag To Selected Strips').text = text
        row = layout.row()
        row.separator()

        tag_index = context.scene.vseqf.strip_tag_index
        if len(strip.tags) > 0:
            if tag_index >= len(strip.tags):
                tag_index = len(strip.tags) - 1
            current_tag = strip.tags[tag_index]

        else:
            current_tag = None
        row = layout.row()
        row.label(text='Active Tags:')
        row.operator('vseqf.quicktags_clear', text='Clear All Tags').mode = 'active'
        split = layout.split(factor=.9)
        split.template_list("VSEQF_UL_QuickTagList", "", strip, 'tags', scene.vseqf, 'strip_tag_index', rows=3)
        col = split.column()
        col.operator('vseqf.quicktags_add_active', text='+').text = 'Tag'
        if current_tag is not None:
            col.operator('vseqf.quicktags_remove', text='-').text = current_tag.text

        if current_tag is not None:
            row = layout.row()
            row.prop(current_tag, 'use_offset', text='Marker Tag')
            if current_tag.use_offset:
                row = layout.row()
                row.label(text=current_tag.text)
                row.prop(current_tag, 'color', text='')
                row = layout.row(align=True)
                row.prop(current_tag, 'offset', text='Tag Offset')
                row.prop(current_tag, 'length', text='Tag Length')


class VSEQF_UL_QuickTagListAll(bpy.types.UIList):
    """Draws a list of tags"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        layout.label(text=item.name)

    def draw_filter(self, context, layout):
        pass


class VSEQF_UL_QuickTagList(bpy.types.UIList):
    """Draws an editable list of tags"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        del context, data, icon, active_data, active_propname
        layout.prop(item, 'text', text='', emboss=False)

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, property):
        del context
        tags = getattr(data, property)
        helper = bpy.types.UI_UL_list
        flt_neworder = helper.sort_items_by_name(tags, 'name')
        return [], flt_neworder


class VSEQFQuickTagsClear(bpy.types.Operator):
    """Clears all tags on the selected and active strips"""

    bl_idname = 'vseqf.quicktags_clear'
    bl_label = 'VSEQF Quick Tags Clear'
    bl_description = 'Clear all tags on all selected strips'

    mode: bpy.props.StringProperty('selected')

    def execute(self, context):
        if self.mode == 'selected':
            strips = timeline.current_selected(context)
            if not strips:
                return {'FINISHED'}
            bpy.ops.ed.undo_push()
            for strip in strips:
                strip.tags.clear()
            populate_selected_tags()
            populate_tags()
        else:
            strip = timeline.current_active(context)
            if not strip:
                return {'FINISHED'}
            bpy.ops.ed.undo_push()
            strip.tags.clear()
            populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsSelect(bpy.types.Operator):
    """Selects strips with the given tag name
    Argument:
        text: String, the name of the tag to find strips with"""

    bl_idname = 'vseqf.quicktags_select'
    bl_label = 'VSEQF Quick Tags Select'
    bl_description = 'Select all strips with this tag'

    text: bpy.props.StringProperty()

    def execute(self, context):
        bpy.ops.ed.undo_push()
        text = self.text
        new_active = None
        strips = timeline.current_strips(context)
        for strip in strips:
            strip.select = False
            for tag in strip.tags:
                if tag.text == text:
                    strip.select = True
                    new_active = strip
                    break
        active = timeline.current_active(context)
        if not active and not active.select and new_active:
            context.scene.sequence_editor.active_strip = new_active
        context.scene.vseqf.current_tag = text
        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsRemoveFrom(bpy.types.Operator):
    """Removes a tag from a specified strip
    Argument:
        tag: String, a tag and strip name separated by a next line"""
    bl_idname = 'vseqf.quicktags_remove_from'
    bl_label = 'VSEQF Quick Tags Remove From'
    bl_description = 'Remove this tag from this strip'

    tag: bpy.props.StringProperty()

    def execute(self, context):
        if '\n' in self.tag:
            text, strip_name = self.tag.split('\n')
            if text and strip_name:
                bpy.ops.ed.undo_push()
                strips = timeline.current_strips(context)
                for strip in strips:
                    if strip.name == strip_name:
                        for index, tag in reversed(list(enumerate(strip.tags))):
                            if tag.text == text:
                                strip.tags.remove(index)

        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsRemoveMarker(bpy.types.Operator):
    """Remove specific tag marker from active strip
    Argument:
        index: Integer, tag index to remove"""
    bl_idname = 'vseqf.quicktags_remove_marker'
    bl_label = 'VSEQF Quick Tags Remove Marker'

    index: bpy.props.IntProperty(0)

    def execute(self, context):
        active = timeline.current_active(context)
        if active:
            if 0 <= self.index < len(active.tags):
                bpy.ops.ed.undo_push()
                active.tags.remove(self.index)
                populate_selected_tags()
                populate_tags()
                context.scene.frame_current = context.scene.frame_current  #hacky way to force update scene, but it works.
        return{'FINISHED'}


class VSEQFQuickTagsRemove(bpy.types.Operator):
    """Remove tags with a specific name from all selected strips
    Argument:
        text: String, tag text to remove"""
    bl_idname = 'vseqf.quicktags_remove'
    bl_label = 'VSEQF Quick Tags Remove'
    bl_description = 'Remove the selected tag from all selected strips'

    text: bpy.props.StringProperty()

    def execute(self, context):
        strips = timeline.current_selected(context)
        active = timeline.current_active(context)
        if active:
            strips.append(active)
        bpy.ops.ed.undo_push()
        for strip in strips:
            for index, tag in reversed(list(enumerate(strip.tags))):
                if tag.text == self.text:
                    strip.tags.remove(index)
        context.scene.frame_current = context.scene.frame_current  #hacky way to force update scene, but it works.
        populate_selected_tags()
        populate_tags()
        return{'FINISHED'}


class VSEQFQuickTagsAdd(bpy.types.Operator):
    """Adds a tag with the given text to the selected strips
    Argument:
        text: String, tag to add"""
    bl_idname = 'vseqf.quicktags_add'
    bl_label = 'VSEQF Quick Tags Add'
    bl_description = 'Add this tag to all selected strips'

    text: bpy.props.StringProperty()

    def execute(self, context):
        text = self.text.replace("\n", '')
        if text:
            bpy.ops.ed.undo_push()
            strips = timeline.current_selected(context)
            for strip in strips:
                tag_found = False
                for tag in strip.tags:
                    if tag.text == text:
                        tag_found = True
                if not tag_found:
                    tag = strip.tags.add()
                    tag.text = text
        return{'FINISHED'}


class VSEQFQuickTagsAddMarker(bpy.types.Operator):
    """Adds a marker tag to the active strip at the current frame"""
    bl_idname = 'vseqf.quicktags_add_marker'
    bl_label = 'VSEQF Quick Tag Marker Add'
    bl_description = 'Add a tag marker to the active strip at the current frame'

    text: bpy.props.StringProperty()

    def execute(self, context):
        text = self.text.replace("\n", '')
        if text:
            bpy.ops.ed.undo_push()
            strip = timeline.current_active(context)
            if strip:
                cursor_position = context.scene.frame_current
                if cursor_position < strip.frame_final_start:
                    cursor_position = strip.frame_final_start
                if cursor_position >= strip.frame_final_end:
                    cursor_position = strip.frame_final_end - 1
                offset = cursor_position - strip.frame_start + 1
                tag = strip.tags.add()
                tag.text = text
                tag.use_offset = True
                tag.offset = int(offset)
        return{'FINISHED'}


class VSEQFQuickTagsAddActive(bpy.types.Operator):
    """Adds a tag with the given text to the active strip
    Argument:
        text: String, tag to add"""
    bl_idname = 'vseqf.quicktags_add_active'
    bl_label = 'VSEQF Quick Tags Add'
    bl_description = 'Add a new tag to the active strip'

    text: bpy.props.StringProperty()

    def execute(self, context):
        text = self.text.replace("\n", '')
        if text:
            bpy.ops.ed.undo_push()
            strip = timeline.current_active(context)
            tag_found = False
            for tag in strip.tags:
                if tag.text == text:
                    tag_found = True
            if not tag_found:
                tag = strip.tags.add()
                tag.text = text
                for index, tag in enumerate(strip.tags):
                    if tag.text == text:
                        context.scene.vseqf.strip_tag_index = index
                        break
        return{'FINISHED'}


class VSEQFTags(bpy.types.PropertyGroup):
    """QuickTags property that stores tag information"""
    text: bpy.props.StringProperty(
        name="Tag Name",
        default="",
        update=auto_populate_tags)
    use_offset: bpy.props.BoolProperty(
        name="Use Frame Offset",
        default=False,
        description="Make this tag a strip marker")
    offset: bpy.props.IntProperty(
        name="Frame Offset",
        min=0,
        default=0,
        description="Marker tag position, starting at strip beginning")
    length: bpy.props.IntProperty(
        name="Frame Length",
        min=1,
        default=1,
        description="Marker tag length")
    color: bpy.props.FloatVectorProperty(
        name="Tag Color",
        size=3,
        min=0,
        max=1,
        subtype='COLOR',
        default=(1.0, 1.0, 1.0))
