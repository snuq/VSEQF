# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

"""
Known Issues:
    Quick 3point causes recursion errors sometimes when adjusting in/out
    Uncut does not work on movieclip type sequences... there appears to be no way of getting the sequence's source file.
    Right now the script cannot apply a vertical zoom level, as far as I can tell this is missing functionality in Blender's python api.

Future Possibilities:
    Add grab mode options for marker moving (press m while grabbing to change, show real-time updates of position)
    Remove multiple drag feature (Apparently it will be implemented in blender at some point?)
    Ripple insert in real-time while grabbing... need to think about how to do this, but I want it!
    Ability to ripple cut beyond the edge of the selected strips to ADD to the clip
    Copy/paste wrapper that copies strip animation data
    Showing a visual offset on the active audio sequence, showing how far out of sync it is from it's video parent

Todo:
    Once the tools panel is implemented in sequencer, rework all panels and menus to make better use of it.

Features:
    Strip parenting
        Have you ever wanted to keep your video and audio strips in sync?  Parenting will let you synchronize strip movements and cuts from one to another.
        You can have chains of child sequences, or parent everything in the sequencer to one strip.
    Strip movement
        When moving strips, press the alt key to toggle ripple mode.  This will automatically move all strips following the selected along with it.
        New snapping options: snap a sequence to the previous, snap sequence ends to the cursor, and more.
        Want to move the second half of the timeline back a second?  Just grab one strip, activate ripple, and move it back.
        Ripple options are available when deleting or cutting strips as well.
    Adding fades
        Quickly add, modify, or remove precise fades to multiple strips.
        Add or modify fades with visual feedback simply by pressing 'f' in the sequencer.
        Add crossfades to multiple strips with a single click.
    Interface additions
        Added panels and menus to provide better access to tools, including a zooms menu, snaps menu, cuts menu and panel, and a compact strip info panel.
    Three point editing
        Use a three point editing style workflow, import strips and set their start and end points with timecodes before dropping them in the timeline.
    Timeline display
        The timeline can now remain centered on the cursor.
        Zoom levels can be saved and recalled, quickly zoom to a visual area of one minute around the cursor, for instance.
    Numpad shortcuts
        Have full control over the timeline and selected strips with the numpad only.
        Control playback speed, move strips around, or move the cursor, even cut strips, all without moving from the numpad.
    Proxy improvements
        Automatically set, or even generate proxies for newly imported strips.
    Working with markers
        Create markers based on named presets, easily add several 'Fix This Later' markers for instance.
        See all marker time indexes in a list, and quickly jump to whichever you wish.
    Sequence Tags
        Add tags to sequences to classify or organize them.  You can see a list of all tags, and select all strips with a specific tag.
    Cutting improvements
        Trim the left or right side of a strip off with a single click, or even ripple back the entire timeline to match that cut.
        Realized you made a cut you didnt want?  Use uncut to rejoin two strips if their positions match up.
    Context menus that are actually contextual
        Context menus will now vary depending on what the mouse is over when activated.
        For instance: click on the cursor to get cursor snapping options, or click on a strip to get options specific to that strip
    Blender bug fixes
        A few small bugs or odd behavior relating to the VSE have been fixed by this addon.
        Making meta strips will now auto-select effect strips tied to the strip, rather than just showing an error message.
        Cutting strips with effect strips applied will now duplicate the effects to both cut strips.
        Cutting strips with a crossfade could cause the crossfade to be applied to the wrong cut strip, it is now applied to the correct strip.  https://developer.blender.org/T50877
    And much more


Changelog:
0.96
    Fixed bug where box select wouldn't work.
    Removed right-click hold menus - too buggy and blocked box select.  New context menu shortcut: '`' and 'w'
    Improved frame skipping
    Fixed bug where cut strips with deleted parents could have their old parent 'replaced' by a new cut
    Fixed bug in fade operator where waveforms for strips with no animation data would vanish
    Removed QuickList
    Fixed a bug where clearing fades could cause an error - thanks jaggz
    Improved fades - should be better about maintaining the original curve, and not leave extra points when fades are cleared
    Refactored code to make it easier to maintain
    Added option to disable/enable child edges following parents
    Rewrote grab and snapping functions, should be more reliable and correct now
    Fixed some bugs in 3point
    Added variable to change skipped frames in Numpad 7 and 8 shortcuts
    Implemented an operator to draw keyframes for active sound strip directly in the vse (press 'V')
    Fixed bug where filled sequencer areas were not detected properly
    Greatly improved strip tags interface, added ability for tags to become strip markers
    Moved some panels to the new 'Sequencer' tab
    Fixed some api bugs introduced from Blender 2.81
    Added proper tooltips to all operators

"""

import os
import bpy
import bgl
import gpu
import math
from bpy_extras.io_utils import ImportHelper
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader

from . import cuts
from . import fades
from . import grabs
from . import markers
from . import parenting
from . import shortcuts
from . import snaps
from . import tags
from . import threepoint
from . import timeline
from . import zoom
from . import vseqf


bl_info = {
    "name": "VSE Quick Functions",
    "description": "Improves functionality of the sequencer by adding new menus and functions for snapping, adding fades, zooming, sequence parenting, ripple editing, playback speed, and more.",
    "author": "Hudson Barkley (Snu/snuq/Aritodo)",
    "version": (0, 9, 6),
    "blender": (2, 81, 0),
    "location": "Sequencer Panels; Sequencer Menus; Sequencer S, F, Shift-F, Z, Ctrl-P, Shift-P, Alt-M, Alt-K Shortcuts",
    "wiki_url": "https://github.com/snuq/VSEQF",
    "tracker_url": "https://github.com/snuq/VSEQF/issues",
    "category": "Sequencer"
}
vseqf_draw_handler = None

classes = []

classes = classes + [cuts.VSEQFCut, cuts.VSEQFQuickCutsMenu, cuts.VSEQF_PT_QuickCutsPanel, cuts.VSEQFDelete,
                     cuts.VSEQFDeleteConfirm, cuts.VSEQFDeleteRippleConfirm]
classes = classes + [fades.VSEQFModalFades, fades.VSEQF_PT_QuickFadesPanel, fades.VSEQFQuickFadesMenu,
                     fades.VSEQFQuickFadesSet, fades.VSEQFQuickFadesClear, fades.VSEQFQuickFadesCross,
                     fades.VSEQFModalVolumeDraw, fades.VSEQF_PT_QuickFadesStripPanel]
classes = classes + [grabs.VSEQFContextMenu, grabs.VSEQFContextCursor, grabs.VSEQFContextMarker, grabs.VSEQFContextNone,
                     grabs.VSEQFContextSequence, grabs.VSEQFDoubleUndo, grabs.VSEQFContextSequenceLeft,
                     grabs.VSEQFContextSequenceRight, grabs.VSEQFGrab, grabs.VSEQFGrabAdd, grabs.VSEQFSelectGrab]
classes = classes + [markers.VSEQF_PT_QuickMarkersPanel, markers.VSEQF_UL_QuickMarkerPresetList,
                     markers.VSEQF_UL_QuickMarkerList, markers.VSEQFQuickMarkerDelete, markers.VSEQFQuickMarkerMove,
                     markers.VSEQFQuickMarkerRename, markers.VSEQFQuickMarkerJump, markers.VSEQFQuickMarkersMenu,
                     markers.VSEQFQuickMarkersPlace, markers.VSEQFQuickMarkersRemovePreset,
                     markers.VSEQFQuickMarkersAddPreset, markers.VSEQFMarkerPreset]
classes = classes + [parenting.VSEQF_PT_Parenting, parenting.VSEQFQuickParentsMenu, parenting.VSEQFQuickParents,
                     parenting.VSEQFQuickParentsClear]
classes = classes + [snaps.VSEQFQuickSnapsMenu, snaps.VSEQFQuickSnaps]
classes = classes + [shortcuts.VSEQFQuickShortcutsNudge, shortcuts.VSEQFQuickShortcutsSpeed,
                     shortcuts.VSEQFQuickShortcutsSkip, shortcuts.VSEQFQuickShortcutsResetPlay]
classes = classes + [tags.VSEQFQuickTagsMenu, tags.VSEQF_PT_QuickTagsPanel, tags.VSEQF_UL_QuickTagListAll,
                     tags.VSEQF_UL_QuickTagList, tags.VSEQFQuickTagsClear, tags.VSEQFQuickTagsSelect,
                     tags.VSEQFQuickTagsRemoveFrom, tags.VSEQFQuickTagsRemove, tags.VSEQFQuickTagsStripMarkerMenu,
                     tags.VSEQFQuickTagsAdd, tags.VSEQFQuickTagsAddActive, tags.VSEQFTags, tags.VSEQFQuickTagsAddMarker,
                     tags.VSEQFQuickTagsRemoveMarker]
classes = classes + [threepoint.VSEQF_PT_ThreePointBrowserPanel, threepoint.VSEQFThreePointImportToClip,
                     threepoint.VSEQF_PT_ThreePointPanel, threepoint.VSEQFThreePointImport,
                     threepoint.VSEQFThreePointOperator, threepoint.VSEQFQuick3PointValues]
classes = classes + [timeline.VSEQFMeta, timeline.VSEQFMetaExit, timeline.VSEQFQuickTimeline,
                     timeline.VSEQFQuickTimelineMenu, timeline.VSEQF_PT_QuickTimelinePanel]
classes = classes + [zoom.VSEQFQuickZoomsMenu, zoom.VSEQFQuickZoomPresetMenu, zoom.VSEQFQuickZoomPreset,
                     zoom.VSEQFClearZooms, zoom.VSEQFRemoveZoom, zoom.VSEQFAddZoom, zoom.VSEQFQuickZooms,
                     zoom.VSEQFZoomPreset]


#Menu draw functions
def draw_quickzoom_menu(self, context):
    """Draws the submenu for the QuickZoom shortcuts, placed in the sequencer view menu"""
    del context
    layout = self.layout
    layout.menu('VSEQF_MT_quickzooms_menu', text="Quick Zoom")


def draw_quickmarker_menu(self, context):
    """Draws the submenu for the QuickMarker presets, placed in the sequencer markers menu"""
    layout = self.layout
    if len(context.scene.vseqf.marker_presets) > 0:
        layout.menu('VSEQF_MT_quickmarkers_menu', text="Quick Markers")


def draw_quicksettings_menu(self, context):
    """Draws the general settings menu for QuickContinuous related functions"""

    del context
    layout = self.layout
    layout.menu('VSEQF_MT_settings_menu', text="Quick Functions Settings")


def draw_follow_header(self, context):
    layout = self.layout
    scene = context.scene
    if context.space_data.view_type != 'PREVIEW':
        layout.prop(scene.vseqf, 'follow', text='Follow Cursor', toggle=True)


def start_follow(_, context):
    if context.scene.vseqf.follow:
        bpy.ops.vseqf.follow('INVOKE_DEFAULT')


class VSEQFFollow(bpy.types.Operator):
    """Modal operator that will center on the play cursor while running."""
    bl_idname = "vseqf.follow"
    bl_label = "Center the playcursor"
    region = None
    view = None
    cursor_target = 0
    animation_playing_last = False
    skip_first_click = True

    _timer = None

    def modal(self, context, event):
        view = self.view
        if not context.scene.vseqf.follow:
            return {'CANCELLED'}
        if context.screen.is_animation_playing and not self.animation_playing_last:
            self.recalculate_target(context)
        if event.type == 'LEFTMOUSE' and context.screen.is_animation_playing:
            if self.skip_first_click:
                self.skip_first_click = False
            else:
                old_x = self.view.view_to_region(context.scene.frame_current, 0, clip=False)[0]
                new_x = event.mouse_region_x
                delta_x = new_x - old_x
                self.cursor_target = self.cursor_target + delta_x

        if event.type == 'TIMER':
            if context.screen.is_animation_playing:
                override = context.copy()
                override['region'] = self.region
                override['view2d'] = self.view
                cursor_location = view.view_to_region(context.scene.frame_current, 0, clip=False)[0]
                if cursor_location != 12000:
                    offset = (self.cursor_target - cursor_location)
                    bpy.ops.view2d.pan(override, deltax=-offset)
        self.animation_playing_last = context.screen.is_animation_playing
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        del event
        self.animation_playing_last = context.screen.is_animation_playing
        if context.screen.is_animation_playing:
            #Need to put this in to prevent blender from changing cursor position when the click that STARTED this is caught
            self.skip_first_click = True
        else:
            self.skip_first_click = False
        area = context.area
        for region in area.regions:
            if region.type == 'WINDOW':
                self.region = region
                self.view = region.view2d
        if self.region is None or self.view is None:
            return {'CANCELLED'}
        if context.screen.is_animation_playing:
            self.recalculate_target(context)
        self._timer = context.window_manager.event_timer_add(time_step=0.25, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def recalculate_target(self, context):
        cursor_location = self.view.view_to_region(context.scene.frame_current, 0, clip=True)[0]
        if cursor_location == 12000:
            self.cursor_target = round(self.region.width / 4)
        else:
            self.cursor_target = cursor_location


class VSEQF_PT_CompactEdit(bpy.types.Panel):
    """Panel for displaying QuickList"""
    bl_label = "Edit Strip Compact"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Strip"

    @classmethod
    def poll(cls, context):
        prefs = vseqf.get_prefs()

        if not timeline.current_active(context):
            return False
        else:
            return prefs.edit

    def draw(self, context):
        prefs = vseqf.get_prefs()
        scene = context.scene
        strip = timeline.current_active(context)
        layout = self.layout
        fps = vseqf.get_fps(scene)

        row = layout.row()
        split = row.split(factor=.8)
        split.prop(strip, 'name', text="")
        split.label(text="("+strip.type+")")

        if strip.type == 'SOUND':
            row = layout.row(align=True)
            sub = row.row(align=True)
            sub.active = not strip.mute
            sub.prop(strip, 'volume', text='Volume')
            row.prop(strip, "mute", toggle=True, icon_only=True)
            row.prop(strip, "lock", toggle=True, icon_only=True)
            row = layout.row()
            row.prop(strip, "pan")
            row.prop(strip, "pitch")
        else:
            row = layout.row(align=True)
            sub = row.row(align=True)
            sub.active = not strip.mute
            split = sub.split(factor=.3, align=True)
            split.prop(strip, "blend_type", text="")
            split.prop(strip, "blend_alpha", text="Opacity", slider=True)
            row.prop(strip, "mute", toggle=True, icon_only=True)
            row.prop(strip, "lock", toggle=True, icon_only=True)
            row = layout.row(align=True)
            row.prop(strip, "color_saturation", text="Saturation")
            row.prop(strip, "color_multiply", text="Multiply")

        col = layout.column()
        sub = col.column()
        sub.enabled = not strip.lock
        row = sub.row(align=True)
        row.prop(strip, "channel")
        row.prop(strip, "frame_start", text="Position: ("+vseqf.timecode_from_frames(strip.frame_final_start, fps)+")")
        row = sub.row()
        row.prop(strip, "frame_final_duration", text="Length: ("+vseqf.timecode_from_frames(strip.frame_final_duration, fps)+")")
        row = sub.row(align=True)
        row.prop(strip, "frame_offset_start", text="In Offset: ("+vseqf.timecode_from_frames(strip.frame_offset_start, fps)+")")
        row.prop(strip, "frame_offset_end", text="Out Offset: ("+vseqf.timecode_from_frames(strip.frame_offset_end, fps)+")")

        if prefs.fades:
            #display info about the fade in and out of the current sequence
            fade_curve = fades.get_fade_curve(context, strip, create=False)
            if fade_curve:
                fadein = fades.fades(fade_curve, strip, 'detect', 'in')
                fadeout = fades.fades(fade_curve, strip, 'detect', 'out')
            else:
                fadein = 0
                fadeout = 0

            row = layout.row()
            if fadein > 0:
                row.label(text="Fadein: "+str(round(fadein))+" Frames")
            else:
                row.label(text="No Fadein Detected")
            if fadeout > 0:
                row.label(text="Fadeout: "+str(round(fadeout))+" Frames")
            else:
                row.label(text="No Fadeout Detected")

        if prefs.parenting:
            #display info about parenting relationships
            sequence = timeline.current_active(context)
            selected = context.selected_sequences
            if len(scene.sequence_editor.meta_stack) > 0:
                #inside a meta strip
                sequencer = scene.sequence_editor.meta_stack[-1]
            else:
                #not inside a meta strip
                sequencer = scene.sequence_editor
            if hasattr(sequencer, 'sequences'):
                sequences = sequencer.sequences
            else:
                sequences = []

            children = parenting.find_children(sequence, sequences=sequences)
            parent = parenting.find_parent(sequence)

            box = layout.box()
            #List relationships for active sequence
            if parent:
                row = box.row()
                split = row.split(factor=.8, align=True)
                split.label(text="Parent: "+parent.name)
                split.operator('vseqf.quickparents', text='', icon="ARROW_LEFTRIGHT").action = 'select_parent'
                split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_parent'
            if len(children) > 0:
                row = box.row()
                split = row.split(factor=.8, align=True)
                subsplit = split.split(factor=.1)
                subsplit.prop(scene.vseqf, 'expanded_children', icon="TRIA_DOWN" if scene.vseqf.expanded_children else "TRIA_RIGHT", icon_only=True, emboss=False)
                subsplit.label(text="Children: "+children[0].name)
                split.operator('vseqf.quickparents', text='', icon="ARROW_LEFTRIGHT").action = 'select_children'
                split.operator('vseqf.quickparents', text='', icon="X").action = 'clear_children'
                if scene.vseqf.expanded_children:
                    index = 1
                    while index < len(children):
                        row = box.row()
                        split = row.split(factor=.1)
                        split.label(text='')
                        split.label(text=children[index].name)
                        index = index + 1

            row = box.row()
            split = row.split()
            split.operator('vseqf.quickparents', text='Set Active As Parent').action = 'add'
            if len(selected) <= 1:
                split.enabled = False
            row.prop(scene.vseqf, 'children', toggle=True)
            row = box.row()
            row.prop(scene.vseqf, 'select_children', toggle=True)
            row.prop(scene.vseqf, 'delete_children', toggle=True)


class VSEQFImport(bpy.types.Operator, ImportHelper):
    """Loads different types of files into the sequencer"""
    bl_idname = 'vseqf.import_strip'
    bl_label = 'Import Strip'

    type: bpy.props.EnumProperty(
        name="Import Type",
        items=(('MOVIE', 'Movie', ""), ("IMAGE", "Image", "")),
        default='MOVIE')

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)

    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True)
    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        description="Start frame of the sequence strip",
        default=0)
    channel: bpy.props.IntProperty(
        name="Channel",
        description="Channel to place this strip into",
        default=1)
    replace_selection: bpy.props.BoolProperty(
        name="Replace Selection",
        description="Replace the current selection",
        default=True)
    sound: bpy.props.BoolProperty(
        name="Sound",
        description="Load sound with the movie",
        default=True)
    use_movie_framerate: bpy.props.BoolProperty(
        name="Use Movie Framerate",
        description="Use framerate from the movie to keep sound and video in sync",
        default=False)
    import_location: bpy.props.EnumProperty(
        name="Import At",
        description="Location to import strips at",
        items=(("IMPORT_FRAME", "Import At Frame", ""), ("INSERT_FRAME", "Insert At Frame", ""), ("CUT_INSERT", "Cut And Insert At Frame", ""), ("END", "Import At End", "")),
        default="IMPORT_FRAME")
    autoparent: bpy.props.BoolProperty(
        name="Auto-Parent A/V",
        description="Automatically parent audio strips to their movie strips",
        default=True)
    autoproxy: bpy.props.BoolProperty(
        name="Auto-Set Proxy",
        description="Automatically enable proxy settings",
        default=False)
    autogenerateproxy: bpy.props.BoolProperty(
        name="Auto-Generate Proxy",
        description="Automatically generate proxies for imported strips",
        default=False)
    use_placeholders: bpy.props.BoolProperty(
        name="Use Placeholders",
        description="Use placeholders for missing frames of the strip",
        default=False)
    length: bpy.props.IntProperty(
        name="Image Length",
        description="Length in frames to use for a single imported image",
        default=30)
    filename: bpy.props.StringProperty(
        name="Filename",
        description="File with path, used when files is not set."
    )
    frame = 0
    to_parent = []
    all_imported = []

    def draw(self, context):
        prefs = vseqf.get_prefs()
        context.space_data.params.use_filter = True
        context.space_data.params.use_filter_folder = True
        if self.type == 'MOVIE':
            context.space_data.params.use_filter_movie = True
            layout = self.layout
            layout.prop(self, 'relative_path')
            layout.prop(self, 'start_frame')
            layout.prop(self, 'channel')
            layout.prop(self, 'import_location')
            layout.prop(self, 'replace_selection')
            layout.prop(self, 'sound')
            layout.prop(self, 'use_movie_framerate')
            if vseqf.parenting():
                layout.prop(self, 'autoparent')
            if prefs.proxy:
                layout.prop(self, 'autoproxy')
                layout.prop(self, 'autogenerateproxy')
        elif self.type == 'IMAGE':
            context.space_data.params.use_filter_image = True
            layout = self.layout
            number_of_files = len(self.files)
            row = layout.row()
            row.prop(self, 'relative_path')
            row = layout.row()
            row.prop(self, 'start_frame')
            row = layout.row()
            if number_of_files > 1:
                row.label(text="Length: "+str(number_of_files))
            else:
                row.prop(self, 'length')
            row = layout.row()
            row.prop(self, 'channel')
            row = layout.row()
            row.prop(self, 'import_location')
            row = layout.row()
            row.prop(self, 'replace_selection')
            if prefs.proxy:
                layout.prop(self, 'autoproxy')
                layout.prop(self, 'autogenerateproxy')

    def invoke(self, context, event):
        del event
        sequencer = context.scene.sequence_editor
        if not sequencer:
            context.scene.sequence_editor_create()
        if self.type == 'MOVIE':
            self.bl_label = 'Add Movie Strip'
        elif self.type == 'IMAGE':
            self.bl_label = 'Add Image'
        scene = context.scene
        prefs = vseqf.get_prefs()
        fps = vseqf.get_fps(context.scene)
        self.length = fps * 4
        self.start_frame = context.scene.frame_current
        if len(context.scene.sequence_editor.sequences_all) == 0:
            self.use_movie_framerate = True
        if prefs.parenting and scene.vseqf.children:
            self.autoparent = scene.vseqf.autoparent
        else:
            self.autoparent = False
        if prefs.proxy:
            self.autoproxy = scene.vseqf.enable_proxy
            self.autogenerateproxy = scene.vseqf.build_proxy
        else:
            self.autoproxy = False
            self.autogenerateproxy = False
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def find_end_frame(self, sequences):
        frame = 1
        for sequence in sequences:
            if sequence.frame_final_end > frame:
                frame = sequence.frame_final_end
        return frame

    def setup_proxies(self, sequences):
        for sequence in sequences:
            vseqf.apply_proxy_settings(sequence)

    def execute(self, context):
        sequencer = context.scene.sequence_editor
        if not sequencer:
            context.scene.sequence_editor_create()
        bpy.ops.ed.undo_push()
        old_snap_new_end = context.scene.vseqf.snap_new_end
        context.scene.vseqf.snap_new_end = False  #disable this so the continuous function doesnt do weird stuff while importing this
        selected = timeline.current_selected(context)
        active = timeline.current_active(context)
        end_frame = self.find_end_frame(timeline.current_sequences(context))
        dirname = os.path.dirname(bpy.path.abspath(self.filepath))
        bpy.ops.sequencer.select_all(action='DESELECT')
        if self.import_location in ['END', 'INSERT_FRAME', 'CUT_INSERT']:
            self.frame = end_frame
        else:
            self.frame = self.start_frame
        self.all_imported = []
        self.to_parent = []
        last_frame = context.scene.frame_current
        if self.type == 'MOVIE':
            if self.files:
                #iterate through files and import them
                for file in self.files:
                    filename = os.path.join(dirname, file.name)
                    self.import_movie(context, filename)
            else:
                self.import_movie(context, self.filename)
        elif self.type == 'IMAGE':
            files = [{"name": i.name} for i in self.files]
            if len(self.files) > 1:
                length = len(self.files)
            else:
                length = self.length
            bpy.ops.sequencer.image_strip_add(directory=dirname, files=files, relative_path=self.relative_path, frame_start=self.frame, frame_end=self.frame+length-1, channel=self.channel, replace_sel=True, use_placeholders=self.use_placeholders)
            imported = timeline.current_selected(context)
            self.all_imported.extend(imported)
        if self.import_location == 'INSERT_FRAME' or self.import_location == 'CUT_INSERT':
            new_end_frame = self.find_end_frame(timeline.current_sequences(context))
            move_forward = new_end_frame - end_frame
            move_back = end_frame - self.start_frame + move_forward
            if self.import_location == 'INSERT_FRAME':
                cut_type = 'INSERT_ONLY'
            else:
                cut_type = 'INSERT'
            bpy.ops.vseqf.cut(type=cut_type, use_insert=True, insert=move_forward, use_all=True, all=True)
            for sequence in self.all_imported:
                sequence.frame_start = sequence.frame_start - move_back
        if self.sound and self.autoparent:
            #autoparent audio strips to video
            for pair in self.to_parent:
                movie, sound = pair
                parenting.add_children(movie, [sound])
        if self.autoproxy:
            #auto-set proxy settings
            self.setup_proxies(self.all_imported)
        if not self.replace_selection:
            bpy.ops.sequencer.select_all(action='DESELECT')
            for sequence in selected:
                sequence.select = True
            if active:
                context.scene.sequence_editor.active_strip = active
        else:
            bpy.ops.sequencer.select_all(action='DESELECT')
            for sequence in self.all_imported:
                sequence.select = True
        if self.autoproxy and self.autogenerateproxy and not context.scene.vseqf.build_proxy:
            bpy.ops.sequencer.rebuild_proxy('INVOKE_DEFAULT')
        for file in self.all_imported:
            if file.frame_final_end > last_frame:
                last_frame = file.frame_final_end
        if old_snap_new_end:
            context.scene.frame_current = last_frame
        context.scene.vseqf.snap_new_end = old_snap_new_end
        return {'FINISHED'}

    def import_movie(self, context, filename):
        bpy.ops.sequencer.movie_strip_add(filepath=filename, frame_start=self.frame, relative_path=self.relative_path, channel=self.channel, replace_sel=True, sound=self.sound, use_framerate=self.use_movie_framerate)
        imported = timeline.current_selected(context)
        if len(imported) > 1:
            #this included a sound strip, maybe other types?
            moviestrip = False
            soundstrip = False
            otherstrips = []
            for seq in imported:
                if seq.type == 'MOVIE':
                    moviestrip = seq
                elif seq.type == 'SOUND':
                    soundstrip = seq
                else:
                    otherstrips.append(seq)
                if seq.frame_final_end > self.frame:
                    self.frame = seq.frame_final_end
            if moviestrip and soundstrip:
                #Attempt to fix a blender bug where it puts the audio strip too low - https://developer.blender.org/T64964
                frame_start = moviestrip.frame_start
                sound_channel = moviestrip.channel
                moviestrip.channel = moviestrip.channel + 1
                moviestrip.frame_start = frame_start
                soundstrip.channel = sound_channel
                self.to_parent.append([moviestrip, soundstrip])
        else:
            self.frame = imported[0].frame_final_end
        self.all_imported.extend(imported)


#Functions related to continuous update
@persistent
def vseqf_continuous(scene):
    if not bpy.context.scene or bpy.context.scene != scene:
        return
    if scene.vseqf.last_frame != scene.frame_current:
        #scene frame was changed, assume nothing else happened
        pass
        #scene.vseqf.last_frame = scene.frame_current
    else:
        #something in the scene was changed by the user, figure out what
        try:
            sequencer = scene.sequence_editor
            sequences = sequencer.sequences
        except:
            return
        new_sequences = []
        new_end = scene.frame_current
        build_proxies = False
        for sequence in sequences:
            if sequence.new:
                if not (sequence.type == 'META' or hasattr(sequence, 'input_1')):
                    new_sequences.append(sequence)
                sequence.last_name = sequence.name
                sequence.new = False
            if sequence.last_name != sequence.name:
                #sequence was renamed or duplicated, update parenting if the original doesnt still exist
                if sequence.name and sequence.last_name:
                    original = False
                    for seq in sequences:
                        if seq.name == sequence.last_name:
                            #this sequence was just duplicated or copied, dont do anything
                            original = seq
                            break
                    if not original:
                        #sequence was renamed, update parenting
                        children = parenting.find_children(sequence.last_name, name=True, sequences=sequences)
                        for child in children:
                            child.parent = sequence.name
                sequence.last_name = sequence.name
        if new_sequences:
            for sequence in new_sequences:
                if sequence.type not in ['ADJUSTMENT', 'TEXT', 'COLOR', 'MULTICAM'] and sequence.frame_final_end > new_end:
                    new_end = sequence.frame_final_end
                if vseqf.parenting() and scene.vseqf.autoparent:
                    #autoparent
                    if sequence.type == 'SOUND':
                        for seq in new_sequences:
                            if seq.type == 'MOVIE':
                                if seq.filepath == sequence.sound.filepath:
                                    sequence.parent = seq.name
                                    break
                if vseqf.proxy():
                    #enable proxies on sequence
                    applied_proxies = vseqf.apply_proxy_settings(sequence)
                    if applied_proxies and scene.vseqf.build_proxy:
                        build_proxies = True
            if build_proxies:
                #Build proxies if needed
                last_selected = bpy.context.selected_sequences
                for seq in sequences:
                    if seq in new_sequences:
                        seq.select = True
                    else:
                        seq.select = False
                area = False
                region = False
                for screenarea in bpy.context.window.screen.areas:
                    if screenarea.type == 'SEQUENCE_EDITOR':
                        area = screenarea
                        for arearegion in area.regions:
                            if arearegion.type == 'WINDOW':
                                region = arearegion
                if area and region:
                    override = bpy.context.copy()
                    override['area'] = area
                    override['region'] = region
                    bpy.ops.sequencer.rebuild_proxy(override, 'INVOKE_DEFAULT')
                for seq in sequences:
                    if seq in last_selected:
                        seq.select = True
                    else:
                        seq.select = False
            if scene.vseqf.snap_new_end:
                scene.frame_current = new_end


def vseqf_draw():
    context = bpy.context
    prefs = vseqf.get_prefs()
    colors = bpy.context.preferences.themes[0].user_interface
    text_color = list(colors.wcol_text.text_sel)+[1]
    active_strip = timeline.current_active(context)
    if not active_strip:
        return
    region = bpy.context.region
    view = region.view2d

    #determine pixels per frame and channel
    width = region.width
    height = region.height
    left, bottom = view.region_to_view(0, 0)
    right, top = view.region_to_view(width, height)
    if math.isnan(left):
        return
    shown_width = right - left
    shown_height = top - bottom
    channel_px = height / shown_height
    frame_px = width / shown_width

    min_x = 25
    max_x = width - 10
    fps = vseqf.get_fps()
    draw_strip_info(context, active_strip, fps, frame_px, channel_px, min_x, max_x, view, width, text_color, prefs.fades, prefs.parenting, True, True)
    selected = timeline.current_selected(context)
    for strip in selected:
        if strip != active_strip:
            draw_strip_info(context, strip, fps, frame_px, channel_px, min_x, max_x, view, width, text_color, prefs.fades, prefs.parenting, False, True)


def draw_strip_info(context, active_strip, fps, frame_px, channel_px, min_x, max_x, view, width, text_color, show_fades, show_parenting, show_length, show_markers):
    length = active_strip.frame_final_duration
    active_x = active_strip.frame_final_start + (length / 2)
    active_y = active_strip.channel + 0.5
    active_left, active_top = view.view_to_region(active_strip.frame_final_start, active_strip.channel+1, clip=False)
    active_right, active_bottom = view.view_to_region(active_strip.frame_final_end, active_strip.channel, clip=False)
    active_pos_x, active_pos_y = view.view_to_region(active_x, active_strip.channel + 0.5, clip=False)
    active_width = length * frame_px
    fade_height = channel_px / 20
    text_size = 10
    strip_x = active_pos_x
    if strip_x <= min_x and active_right > min_x:
        strip_x = min_x
    if strip_x >= max_x and active_left < max_x:
        strip_x = max_x

    #display length
    if show_length:
        length_timecode = vseqf.timecode_from_frames(length, fps)
        vseqf.draw_text(strip_x - (strip_x / width) * 40, active_bottom + (channel_px * .1), text_size, '('+length_timecode+')', text_color)

    #display fades
    if show_fades and active_width > text_size * 6:
        fade_curve = fades.get_fade_curve(context, active_strip, create=False)
        if fade_curve:
            fadein = int(fades.fades(fade_curve, active_strip, 'detect', 'in'))
            if fadein and length:
                fadein_percent = fadein / length
                vseqf.draw_rect(active_left, active_top - (fade_height * 2), fadein_percent * active_width, fade_height, color=(.5, .5, 1, .75))
                vseqf.draw_text(active_left, active_top, text_size, 'In: '+str(fadein), text_color)
            fadeout = int(fades.fades(fade_curve, active_strip, 'detect', 'out'))
            if fadeout and length:
                fadeout_percent = fadeout / length
                fadeout_width = active_width * fadeout_percent
                vseqf.draw_rect(active_right - fadeout_width, active_top - (fade_height * 2), fadeout_width, fade_height, color=(.5, .5, 1, .75))
                vseqf.draw_text(active_right - (text_size * 4), active_top, text_size, 'Out: '+str(fadeout), text_color)

    if show_parenting:
        bgl.glEnable(bgl.GL_BLEND)
        children = parenting.find_children(active_strip)
        parent = parenting.find_parent(active_strip)
        if parent:
            parent_x = parent.frame_final_start + (parent.frame_final_duration / 2)
            parent_y = parent.channel + 0.5
            distance_x = parent_x - active_x
            distance_y = parent_y - active_y
            pixel_x_distance = int(distance_x * frame_px)
            pixel_y_distance = int(distance_y * channel_px)
            pixel_x = active_pos_x + pixel_x_distance
            pixel_y = active_pos_y + pixel_y_distance
            vseqf.draw_line(strip_x, active_pos_y, pixel_x, pixel_y, color=(0.0, 0.0, 0.0, 0.2))
        coords = []
        for child in children:
            child_x = child.frame_final_start + (child.frame_final_duration / 2)
            child_y = child.channel + 0.5
            distance_x = child_x - active_x
            distance_y = child_y - active_y
            pixel_x_distance = int(distance_x * frame_px)
            pixel_y_distance = int(distance_y * channel_px)
            pixel_x = active_pos_x + pixel_x_distance
            pixel_y = active_pos_y + pixel_y_distance
            coords.append((strip_x, active_pos_y))
            coords.append((pixel_x, pixel_y))
        shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {'pos': coords})
        shader.bind()
        shader.uniform_float('color', (1.0, 1.0, 1.0, 0.2))
        batch.draw(shader)
        bgl.glDisable(bgl.GL_BLEND)

    if show_markers:
        bgl.glEnable(bgl.GL_BLEND)
        for tag in active_strip.tags:
            if tag.use_offset:
                if active_strip.frame_offset_start < tag.offset <= active_strip.frame_final_duration + active_strip.frame_offset_start - active_strip.frame_still_start:
                    adjusted_offset = tag.offset - 1 - active_strip.frame_offset_start + active_strip.frame_still_start
                    left = active_left + (adjusted_offset * frame_px)
                    width = tag.length * frame_px
                    if left + width > active_right:
                        width = active_right - left
                    bgl.glEnable(bgl.GL_BLEND)
                    vseqf.draw_rect(left, active_bottom, width, channel_px, color=(tag.color[0], tag.color[1], tag.color[2], 0.33))
                    vseqf.draw_text(left, active_top, text_size, tag.text)
        bgl.glDisable(bgl.GL_BLEND)


#Functions related to QuickSpeed
@persistent
def frame_step(scene):
    """Handler that skips frames when the speed step value is used
    Argument:
        scene: the current Scene"""

    if bpy.context.scene != scene:
        return
    if scene.vseqf.step in [-1, 0, 1]:
        return
    difference = scene.frame_current - scene.vseqf.last_frame
    if difference == -1 or difference == 1:
        frame_skip = difference * (abs(scene.vseqf.step) - 1)
        bpy.ops.screen.frame_offset(delta=frame_skip)
    scene.vseqf.last_frame = scene.frame_current


def draw_quickspeed_header(self, context):
    """Draws the speed selector in the sequencer header"""
    layout = self.layout
    scene = context.scene
    self.layout_width = 30
    layout.prop(scene.vseqf, 'step', text="Speed Step")


#Classes for settings and variables
class VSEQFSettingsMenu(bpy.types.Menu):
    """Pop-up menu for settings related to QuickContinuous"""
    bl_idname = "VSEQF_MT_settings_menu"
    bl_label = "Quick Settings"

    def draw(self, context):
        prefs = vseqf.get_prefs()

        layout = self.layout
        scene = context.scene
        layout.prop(scene.vseqf, 'snap_cursor_to_edge')
        layout.prop(scene.vseqf, 'snap_new_end')
        layout.prop(scene.vseqf, 'shortcut_skip')
        if prefs.parenting:
            layout.separator()
            layout.label(text='QuickParenting Settings')
            layout.separator()
            layout.prop(scene.vseqf, 'children')
            layout.prop(scene.vseqf, 'move_edges')
            layout.prop(scene.vseqf, 'delete_children')
            layout.prop(scene.vseqf, 'autoparent')
            layout.prop(scene.vseqf, 'select_children')
        if prefs.proxy:
            layout.separator()
            layout.label(text='QuickProxy Settings')
            layout.separator()
            layout.prop(scene.vseqf, 'enable_proxy')
            layout.prop(scene.vseqf, 'build_proxy')
            layout.prop(scene.vseqf, "proxy_quality", text='Proxy Quality')
            layout.prop(scene.vseqf, "proxy_25", text='Generate 25% Proxy')
            layout.prop(scene.vseqf, "proxy_50", text='Generate 50% Proxy')
            layout.prop(scene.vseqf, "proxy_75", text='Generate 75% Proxy')
            layout.prop(scene.vseqf, "proxy_100", text='Generate 100% Proxy')


class VSEQFSetting(bpy.types.PropertyGroup):
    """Property group to store most VSEQF settings.  This will be assigned to scene.vseqf"""
    zoom_presets: bpy.props.CollectionProperty(type=zoom.VSEQFZoomPreset)
    last_frame: bpy.props.IntProperty(
        name="Last Scene Frame",
        default=1)

    shortcut_skip: bpy.props.IntProperty(
        name="Shortcut Skip Frames",
        default=0,
        min=0,
        description="Number of frames that QuickShortcuts will skip with the numpad 7 and 8 keys.  Setting to 0 will default to one second.")
    follow: bpy.props.BoolProperty(
        name="Cursor Following",
        default=False,
        update=start_follow)

    children: bpy.props.BoolProperty(
        name="Cut/Move Children",
        default=True,
        description="Automatically cut and move child strips along with a parent.")
    autoparent: bpy.props.BoolProperty(
        name="Auto-Parent New Audio To Video",
        default=True,
        description="Automatically parent audio strips to video when importing a movie with both types of strips.")
    select_children: bpy.props.BoolProperty(
        name="Auto-Select Children",
        default=False,
        description="Automatically select child strips when a parent is selected.")
    expanded_children: bpy.props.BoolProperty(default=True)
    delete_children: bpy.props.BoolProperty(
        name="Auto-Delete Children",
        default=False,
        description="Automatically delete child strips when a parent is deleted.")
    move_edges: bpy.props.BoolProperty(
        name="Move Matching Child Edges",
        default=True,
        description="When a child edge matches a parent's, it will be moved when the parent's edge is moved.")

    transition: bpy.props.EnumProperty(
        name="Transition Type",
        default="CROSS",
        items=[("CROSS", "Crossfade", "", 1), ("WIPE", "Wipe", "", 2), ("GAMMA_CROSS", "Gamma Cross", "", 3)])
    fade: bpy.props.IntProperty(
        name="Fade Length",
        default=0,
        min=0,
        description="Default Fade Length In Frames")
    fadein: bpy.props.IntProperty(
        name="Fade In Length",
        default=0,
        min=0,
        description="Current Fade In Length In Frames")
    fadeout: bpy.props.IntProperty(
        name="Fade Out Length",
        default=0,
        min=0,
        description="Current Fade Out Length In Frames")

    enable_proxy: bpy.props.BoolProperty(
        name="Enable Proxy On Import",
        default=False)
    build_proxy: bpy.props.BoolProperty(
        name="Auto-Build Proxy On Import",
        default=False)
    proxy_25: bpy.props.BoolProperty(
        name="25%",
        default=True)
    proxy_50: bpy.props.BoolProperty(
        name="50%",
        default=False)
    proxy_75: bpy.props.BoolProperty(
        name="75%",
        default=False)
    proxy_100: bpy.props.BoolProperty(
        name="100%",
        default=False)
    proxy_quality: bpy.props.IntProperty(
        name="Quality",
        default=90,
        min=1,
        max=100)

    current_marker_frame: bpy.props.IntProperty(
        default=0)
    marker_index: bpy.props.IntProperty(
        name="Marker Display Index",
        default=0)
    marker_presets: bpy.props.CollectionProperty(
        type=markers.VSEQFMarkerPreset)
    expanded_markers: bpy.props.BoolProperty(default=True)
    current_marker: bpy.props.StringProperty(
        name="New Preset",
        default='')
    marker_deselect: bpy.props.BoolProperty(
        name="Deselect New Markers",
        default=True,
        description="Markers added with this interface will not be selected when added")

    zoom_size: bpy.props.IntProperty(
        name='Zoom Amount',
        default=200,
        min=1,
        description="Zoom size in frames",
        update=zoom.zoom_cursor)
    step: bpy.props.IntProperty(
        name="Frame Step",
        default=0,
        min=-4,
        max=4)
    skip_index: bpy.props.IntProperty(
        default=0)

    current_tag: bpy.props.StringProperty(
        name="New Tag",
        default='')
    tags: bpy.props.CollectionProperty(type=tags.VSEQFTags)
    selected_tags: bpy.props.CollectionProperty(type=tags.VSEQFTags)
    show_selected_tags: bpy.props.BoolProperty(
        name="Show Tags For All Selected Sequences",
        default=False)
    tag_index: bpy.props.IntProperty(
        name="Tag Display Index",
        default=0)
    strip_tag_index: bpy.props.IntProperty(
        name="Strip Tag Display Index",
        default=0)

    quickcuts_insert: bpy.props.IntProperty(
        name="Frames To Insert",
        default=0,
        min=0,
        description='Number of frames to insert when performing an insert cut')
    quickcuts_all: bpy.props.BoolProperty(
        name='Cut All Sequences',
        default=False,
        description='Cut all sequences, regardless of selection (not including locked sequences)')
    snap_new_end: bpy.props.BoolProperty(
        name='Snap Cursor To End Of New Sequences',
        default=False)
    snap_cursor_to_edge: bpy.props.BoolProperty(
        name='Snap Cursor When Dragging Edges',
        default=False)


class VSEQuickFunctionSettings(bpy.types.AddonPreferences):
    """Addon preferences for QuickFunctions, used to enable and disable features"""
    bl_idname = __name__
    parenting: bpy.props.BoolProperty(
        name="Enable Quick Parenting",
        default=True)
    fades: bpy.props.BoolProperty(
        name="Enable Quick Fades",
        default=True)
    proxy: bpy.props.BoolProperty(
        name="Enable Quick Proxy",
        default=True)
    markers: bpy.props.BoolProperty(
        name="Enable Quick Markers",
        default=True)
    tags: bpy.props.BoolProperty(
        name="Enable Quick Tags",
        default=True)
    cuts: bpy.props.BoolProperty(
        name="Enable Quick Cuts",
        default=True)
    edit: bpy.props.BoolProperty(
        name="Enable Compact Edit Panel",
        default=False)
    threepoint: bpy.props.BoolProperty(
        name="Enable Quick Three Point",
        default=True)

    def draw(self, context):
        del context
        layout = self.layout
        layout.prop(self, "parenting")
        layout.prop(self, "fades")
        layout.prop(self, "proxy")
        layout.prop(self, "markers")
        layout.prop(self, "tags")
        layout.prop(self, "cuts")
        layout.prop(self, "edit")
        layout.prop(self, "threepoint")


#Replaced Blender Menus
class SEQUENCER_MT_strip_transform(bpy.types.Menu):
    bl_label = "Transform"

    def draw(self, context):
        layout = self.layout

        #layout.operator("transform.seq_slide", text="Move")
        layout.operator("vseqf.grab", text="Grab/Move")
        #layout.operator("transform.transform", text="Move/Extend from Playhead").mode = 'TIME_EXTEND'
        layout.operator("vseqf.grab", text="Move/Extend from frame").mode = 'TIME_EXTEND'
        #layout.operator("sequencer.slip", text="Slip Strip Contents")
        layout.operator("vseqf.grab", text="Slip Strip Contents").mode = 'SLIP'

        layout.separator()
        #layout.operator("sequencer.snap")
        layout.operator("sequencer.offset_clear")

        layout.separator()
        layout.operator_menu_enum("sequencer.swap", "side")

        layout.separator()
        layout.operator("sequencer.gap_remove").all = False
        layout.operator("sequencer.gap_insert")

        layout.separator()
        layout.operator('vseqf.quicksnaps', text='Snap Beginning To Cursor').type = 'begin_to_cursor'
        layout.operator('vseqf.quicksnaps', text='Snap End To Cursor').type = 'end_to_cursor'
        layout.operator('vseqf.quicksnaps', text='Snap To Previous Strip').type = 'sequence_to_previous'
        layout.operator('vseqf.quicksnaps', text='Snap To Next Strip').type = 'sequence_to_next'


class SEQUENCER_MT_strip(bpy.types.Menu):
    bl_label = "Strip"

    def draw(self, context):
        layout = self.layout

        layout.operator_context = 'INVOKE_REGION_WIN'

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_transform")

        layout.separator()
        #layout.operator("sequencer.cut", text="Cut").type = 'SOFT'
        #layout.operator("sequencer.cut", text="Hold Cut").type = 'HARD'
        layout.operator("vseqf.cut", text="Cut").type = 'SOFT'
        layout.operator("vseqf.cut", text="Hold Cut").type = 'HARD'

        layout.separator()
        layout.operator("sequencer.copy", text="Copy")
        layout.operator("sequencer.paste", text="Paste")
        layout.operator("sequencer.duplicate_move")
        layout.operator("sequencer.delete", text="Delete...")

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_lock_mute")

        #strip = act_strip(context)
        strip = timeline.current_active(context)

        if strip:
            strip_type = strip.type

            if strip_type != 'SOUND':
                layout.separator()
                layout.operator_menu_enum("sequencer.strip_modifier_add", "type", text="Add Modifier")
                layout.operator("sequencer.strip_modifier_copy", text="Copy Modifiers to Selection")

            if strip_type in {
                    'CROSS', 'ADD', 'SUBTRACT', 'ALPHA_OVER', 'ALPHA_UNDER',
                    'GAMMA_CROSS', 'MULTIPLY', 'OVER_DROP', 'WIPE', 'GLOW',
                    'TRANSFORM', 'COLOR', 'SPEED', 'MULTICAM', 'ADJUSTMENT',
                    'GAUSSIAN_BLUR',
            }:
                layout.separator()
                layout.menu("SEQUENCER_MT_strip_effect")
            elif strip_type == 'MOVIE':
                layout.separator()
                layout.menu("SEQUENCER_MT_strip_movie")
            elif strip_type == 'IMAGE':
                layout.separator()
                layout.operator("sequencer.rendersize")
                layout.operator("sequencer.images_separate")
            elif strip_type == 'TEXT':
                layout.separator()
                layout.menu("SEQUENCER_MT_strip_effect")
            elif strip_type == 'META':
                layout.separator()
                #layout.operator("sequencer.meta_make")
                layout.operator("vseqf.meta_make")
                layout.operator("sequencer.meta_separate")
                layout.operator("sequencer.meta_toggle", text="Toggle Meta")
            if strip_type != 'META':
                layout.separator()
                #layout.operator("sequencer.meta_make")
                layout.operator("vseqf.meta_make")
                layout.operator("sequencer.meta_toggle", text="Toggle Meta")

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_lock_mute")

        layout.separator()
        layout.menu("SEQUENCER_MT_strip_input")

        layout.separator()
        layout.operator("sequencer.rebuild_proxy")


def selected_sequences_len(context):
    try:
        return len(context.selected_sequences) if context.selected_sequences else 0
    except AttributeError:
        return 0


class SEQUENCER_MT_add(bpy.types.Menu):
    bl_label = "Add"

    def draw(self, context):

        layout = self.layout
        layout.operator_context = 'INVOKE_REGION_WIN'

        bpy_data_scenes_len = len(bpy.data.scenes)
        if bpy_data_scenes_len > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.scene_strip_add", text="Scene...", icon='SCENE_DATA')
        elif bpy_data_scenes_len > 1:
            layout.operator_menu_enum("sequencer.scene_strip_add", "scene", text="Scene", icon='SCENE_DATA')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Scene", icon='SCENE_DATA')
        del bpy_data_scenes_len

        bpy_data_movieclips_len = len(bpy.data.movieclips)
        if bpy_data_movieclips_len > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.movieclip_strip_add", text="Clip...", icon='TRACKER')
        elif bpy_data_movieclips_len > 0:
            layout.operator_menu_enum("sequencer.movieclip_strip_add", "clip", text="Clip", icon='TRACKER')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Clip", icon='TRACKER')
        del bpy_data_movieclips_len

        bpy_data_masks_len = len(bpy.data.masks)
        if bpy_data_masks_len > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.mask_strip_add", text="Mask...", icon='MOD_MASK')
        elif bpy_data_masks_len > 0:
            layout.operator_menu_enum("sequencer.mask_strip_add", "mask", text="Mask", icon='MOD_MASK')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Mask", icon='MOD_MASK')
        del bpy_data_masks_len

        layout.separator()

        #layout.operator("sequencer.movie_strip_add", text="Movie", icon='FILE_MOVIE')
        layout.operator("vseqf.import_strip", text="Movie", icon="FILE_MOVIE").type = 'MOVIE'
        #layout.operator("sequencer.sound_strip_add", text="Sound", icon='FILE_SOUND')
        layout.operator("sequencer.sound_strip_add", text="Sound", icon='FILE_SOUND')
        #layout.operator("sequencer.image_strip_add", text="Image/Sequence", icon='FILE_IMAGE')
        layout.operator("vseqf.import_strip", text="Image/Sequence", icon="FILE_IMAGE").type = 'IMAGE'

        layout.separator()

        layout.operator_context = 'INVOKE_REGION_WIN'
        layout.operator("sequencer.effect_strip_add", text="Color", icon='COLOR').type = 'COLOR'
        layout.operator("sequencer.effect_strip_add", text="Text", icon='FONT_DATA').type = 'TEXT'

        layout.separator()

        layout.operator("sequencer.effect_strip_add", text="Adjustment Layer", icon='COLOR').type = 'ADJUSTMENT'

        layout.operator_context = 'INVOKE_DEFAULT'
        layout.menu("SEQUENCER_MT_add_effect", icon='SHADERFX')

        col = layout.column()
        col.menu("SEQUENCER_MT_add_transitions", icon='ARROW_LEFTRIGHT')
        col.enabled = selected_sequences_len(context) >= 2

        col = layout.column()
        col.operator_menu_enum("sequencer.fades_add", "type", text="Fade", icon="IPO_EASE_IN_OUT")
        col.enabled = selected_sequences_len(context) >= 1


#Register properties, operators, menus and shortcuts
classes = classes + [VSEQFSettingsMenu, VSEQFSetting, VSEQFFollow, VSEQFImport, VSEQF_PT_CompactEdit,
                     SEQUENCER_MT_strip, SEQUENCER_MT_strip_transform, SEQUENCER_MT_add]


def register_keymaps():
    if bpy.context.window_manager.keyconfigs.addon:
        keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Sequencer', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
        keymapitems = keymap.keymap_items

        for keymapitem in keymapitems:
            #Iterate through keymaps and delete old shortcuts
            if (keymapitem.type == 'Z') | (keymapitem.type == 'F') | (keymapitem.type == 'S') | (keymapitem.type == 'G') | (keymapitem.type == 'W') | (keymapitem.type == 'LEFTMOUSE') | (keymapitem.type == 'RIGHTMOUSE') | (keymapitem.type == 'K') | (keymapitem.type == 'E') | (keymapitem.type == 'X') | (keymapitem.type == 'DEL') | (keymapitem.type == 'M'):
                keymapitems.remove(keymapitem)
        keymapmarker = keymapitems.new('wm.call_menu', 'M', 'PRESS', alt=True)
        keymapmarker.properties.name = 'VSEQF_MT_quickmarkers_menu'
        keymapstripmarker = keymapitems.new('wm.call_menu', 'M', 'PRESS', shift=True)
        keymapstripmarker.properties.name = 'VSEQF_MT_quickmarkers_strip_menu'
        keymapitems.new('vseqf.meta_make', 'G', 'PRESS', ctrl=True)
        keymapzoom = keymapitems.new('wm.call_menu', 'Z', 'PRESS')
        keymapzoom.properties.name = 'VSEQF_MT_quickzooms_menu'
        keymapitems.new('vseqf.modal_fades', 'F', 'PRESS')
        keymapfademenu = keymapitems.new('wm.call_menu', 'F', 'PRESS', shift=True)
        keymapfademenu.properties.name = 'VSEQF_MT_quickfades_menu'
        keymapitems.new('vseqf.volume_draw', 'V', 'PRESS')
        keymapsnap = keymapitems.new('wm.call_menu', 'S', 'PRESS')
        keymapsnapto = keymapitems.new('vseqf.quicksnaps', 'S', 'PRESS', shift=True)
        keymapsnapto.properties.type = 'selection_to_cursor'
        keymapsnap.properties.name = 'VSEQF_MT_quicksnaps_menu'
        keymapparent = keymapitems.new('wm.call_menu', 'P', 'PRESS', ctrl=True)
        keymapparent.properties.name = 'VSEQF_MT_quickparents_menu'
        keymapparentselect = keymapitems.new('vseqf.quickparents', 'P', 'PRESS', shift=True)
        keymapparentselect.properties.action = 'select_children'

        keymapcuts = keymapitems.new('wm.call_menu', 'K', 'PRESS', ctrl=True)
        keymapcuts.properties.name = 'VSEQF_MT_quickcuts_menu'
        keymapitems.new('vseqf.cut', 'K', 'PRESS')
        keymapcuthard = keymapitems.new('vseqf.cut', 'K', 'PRESS', shift=True)
        keymapcuthard.properties.type = 'HARD'
        keymapcutripple = keymapitems.new('vseqf.cut', 'K', 'PRESS', alt=True)
        keymapcutripple.properties.type = 'RIPPLE'
        keymapcuttrim = keymapitems.new('vseqf.cut', 'K', 'PRESS', alt=True, shift=True)
        keymapcuttrim.properties.type = 'TRIM'

        keymapitems.new('vseqf.grab', 'G', 'PRESS')
        keymapitems.new('vseqf.context_menu', 'ACCENT_GRAVE', 'PRESS')
        keymapitems.new('vseqf.context_menu', 'W', 'PRESS')
        keymapitems.new('vseqf.select_grab', 'LEFTMOUSE', 'PRESS')
        keymapitems.new('vseqf.select_grab', 'RIGHTMOUSE', 'PRESS')

        keymapgrabextend = keymapitems.new('vseqf.grab', 'E', 'PRESS')
        keymapgrabextend.properties.mode = 'TIME_EXTEND'
        keymapslip = keymapitems.new('vseqf.grab', 'S', 'PRESS', alt=True)
        keymapslip.properties.mode = 'SLIP'
        keymapdelete1 = keymapitems.new('wm.call_menu', 'X', 'PRESS')
        keymapdelete1.properties.name = 'VSEQF_MT_delete_menu'
        keymapdelete2 = keymapitems.new('wm.call_menu', 'DEL', 'PRESS')
        keymapdelete2.properties.name = 'VSEQF_MT_delete_menu'
        keymapdelete3 = keymapitems.new('wm.call_menu', 'X', 'PRESS', alt=True)
        keymapdelete3.properties.name = 'VSEQF_MT_delete_ripple_menu'
        keymapdelete4 = keymapitems.new('wm.call_menu', 'DEL', 'PRESS', alt=True)
        keymapdelete4.properties.name = 'VSEQF_MT_delete_ripple_menu'

        #QuickShortcuts Shortcuts
        keymapitems.new('vseqf.cut', 'NUMPAD_SLASH', 'PRESS')
        keymapitem = keymapitems.new('wm.call_menu', 'NUMPAD_SLASH', 'PRESS', ctrl=True)
        keymapitem.properties.name = 'VSEQF_MT_quickcuts_menu'
        keymapitem = keymapitems.new('vseqf.cut', 'NUMPAD_SLASH', 'PRESS', alt=True)
        keymapitem.properties.type = 'RIPPLE'
        keymapitem = keymapitems.new('vseqf.cut', 'NUMPAD_SLASH', 'PRESS', shift=True)
        keymapitem.properties.type = 'TRIM'

        #Numpad: basic movement and playback
        keymapitem = keymapitems.new('screen.frame_offset', 'NUMPAD_1', 'PRESS')
        keymapitem.properties.delta = -1
        keymapitem = keymapitems.new('screen.frame_offset', 'NUMPAD_3', 'PRESS')
        keymapitem.properties.delta = 1
        keymapitem = keymapitems.new('vseqf.change_speed', 'NUMPAD_4', 'PRESS')
        keymapitem.properties.speed_change = 'DOWN'
        keymapitem = keymapitems.new('vseqf.change_speed', 'NUMPAD_6', 'PRESS')
        keymapitem.properties.speed_change = 'UP'
        keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_7', 'PRESS')
        keymapitem.properties.type = 'LASTSECOND'
        keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_9', 'PRESS')
        keymapitem.properties.type = 'NEXTSECOND'
        keymapitems.new('vseqf.reset_playback', 'NUMPAD_5', 'PRESS')

        #Numpad + Ctrl: Advanced movement/jumps
        keymapitem = keymapitems.new('screen.keyframe_jump', 'NUMPAD_1', 'PRESS', ctrl=True)
        keymapitem.properties.next = False
        keymapitem = keymapitems.new('screen.keyframe_jump', 'NUMPAD_3', 'PRESS', ctrl=True)
        keymapitem.properties.next = True
        keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_4', 'PRESS', ctrl=True)
        keymapitem.properties.type = 'LASTEDGE'
        keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_6', 'PRESS', ctrl=True)
        keymapitem.properties.type = 'NEXTEDGE'
        keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_7', 'PRESS', ctrl=True)
        keymapitem.properties.type = 'LASTMARKER'
        keymapitem = keymapitems.new('vseqf.skip_timeline', 'NUMPAD_9', 'PRESS', ctrl=True)
        keymapitem.properties.type = 'NEXTMARKER'

        #Numpad + Alt: Move selected strips
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_1', 'PRESS', alt=True)
        keymapitem.properties.direction = 'LEFT'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_3', 'PRESS', alt=True)
        keymapitem.properties.direction = 'RIGHT'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_4', 'PRESS', alt=True)
        keymapitem.properties.direction = 'LEFT-M'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_6', 'PRESS', alt=True)
        keymapitem.properties.direction = 'RIGHT-M'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_7', 'PRESS', alt=True)
        keymapitem.properties.direction = 'LEFT-L'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_9', 'PRESS', alt=True)
        keymapitem.properties.direction = 'RIGHT-L'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_2', 'PRESS', alt=True)
        keymapitem.properties.direction = 'DOWN'
        keymapitem = keymapitems.new('vseqf.nudge_selected', 'NUMPAD_8', 'PRESS', alt=True)
        keymapitem.properties.direction = 'UP'
        keymapitems.new('vseqf.grab', 'NUMPAD_5', 'PRESS', alt=True)

        #Numpad + Shift: Zoom viewport
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_1', 'PRESS', shift=True)
        keymapitem.properties.area = '2'
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_2', 'PRESS', shift=True)
        keymapitem.properties.area = '10'
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_3', 'PRESS', shift=True)
        keymapitem.properties.area = '30'
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_4', 'PRESS', shift=True)
        keymapitem.properties.area = '60'
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_5', 'PRESS', shift=True)
        keymapitem.properties.area = '120'
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_6', 'PRESS', shift=True)
        keymapitem.properties.area = '300'
        keymapitem = keymapitems.new('vseqf.quickzooms', 'NUMPAD_7', 'PRESS', shift=True)
        keymapitem.properties.area = '600'
        keymapitems.new('sequencer.view_selected', 'NUMPAD_8', 'PRESS', shift=True)
        keymapitems.new('sequencer.view_all', 'NUMPAD_9', 'PRESS', shift=True)


def register():
    bpy.utils.register_class(VSEQuickFunctionSettings)

    #Register classes
    for cls in classes:
        bpy.utils.register_class(cls)

    global vseqf_draw_handler
    if vseqf_draw_handler:
        try:
            bpy.types.SpaceSequenceEditor.draw_handler_remove(vseqf_draw_handler, 'WINDOW')
        except:
            pass
    vseqf_draw_handler = bpy.types.SpaceSequenceEditor.draw_handler_add(vseqf_draw, (), 'WINDOW', 'POST_PIXEL')

    #Add menus
    bpy.types.SEQUENCER_HT_header.append(draw_quickspeed_header)
    bpy.types.SEQUENCER_HT_header.append(draw_follow_header)
    bpy.types.SEQUENCER_MT_view.append(draw_quickzoom_menu)
    bpy.types.SEQUENCER_MT_view.prepend(draw_quicksettings_menu)
    bpy.types.SEQUENCER_MT_marker.prepend(draw_quickmarker_menu)

    #New variables
    bpy.types.Scene.vseqf_skip_interval = bpy.props.IntProperty(default=0, min=0)
    bpy.types.Sequence.parent = bpy.props.StringProperty()
    bpy.types.Sequence.tags = bpy.props.CollectionProperty(type=tags.VSEQFTags)
    bpy.types.Scene.vseqf = bpy.props.PointerProperty(type=VSEQFSetting)
    bpy.types.MovieClip.import_settings = bpy.props.PointerProperty(type=threepoint.VSEQFQuick3PointValues)
    bpy.types.Sequence.new = bpy.props.BoolProperty(default=True)
    bpy.types.Sequence.last_name = bpy.props.StringProperty()

    #Register shortcuts
    register_keymaps()

    #Register handler
    handlers = bpy.app.handlers.frame_change_post
    for handler in handlers:
        if " frame_step " in str(handler):
            handlers.remove(handler)
    handlers.append(frame_step)
    handlers = bpy.app.handlers.depsgraph_update_post
    for handler in handlers:
        if " vseqf_continuous " in str(handler):
            handlers.remove(handler)
    handlers.append(vseqf_continuous)


def unregister():
    global vseqf_draw_handler
    bpy.types.SpaceSequenceEditor.draw_handler_remove(vseqf_draw_handler, 'WINDOW')

    #Unregister menus
    bpy.types.SEQUENCER_HT_header.remove(draw_quickspeed_header)
    bpy.types.SEQUENCER_MT_view.remove(draw_quickzoom_menu)
    bpy.types.SEQUENCER_MT_view.remove(draw_quicksettings_menu)
    bpy.types.SEQUENCER_HT_header.remove(draw_follow_header)

    #Remove shortcuts
    keymapitems = bpy.context.window_manager.keyconfigs.addon.keymaps['Sequencer'].keymap_items
    for keymapitem in keymapitems:
        if (keymapitem.type == 'Z') | (keymapitem.type == 'F') | (keymapitem.type == 'S') | (keymapitem.type == 'G') | (keymapitem.type == 'RIGHTMOUSE') | (keymapitem.type == 'K') | (keymapitem.type == 'E') | (keymapitem.type == 'X') | (keymapitem.type == 'DEL') | (keymapitem.type == 'M') | (keymapitem.type == 'NUMPAD_0') | (keymapitem.type == 'NUMPAD_1') | (keymapitem.type == 'NUMPAD_2') | (keymapitem.type == 'NUMPAD_3') | (keymapitem.type == 'NUMPAD_4') | (keymapitem.type == 'NUMPAD_5') | (keymapitem.type == 'NUMPAD_6') | (keymapitem.type == 'NUMPAD_7') | (keymapitem.type == 'NUMPAD_8') | (keymapitem.type == 'NUMPAD_9'):
            keymapitems.remove(keymapitem)

    #Remove handlers for modal operators
    handlers = bpy.app.handlers.frame_change_post
    for handler in handlers:
        if " frame_step " in str(handler):
            handlers.remove(handler)
    handlers = bpy.app.handlers.depsgraph_update_post
    for handler in handlers:
        if " vseqf_continuous " in str(handler):
            handlers.remove(handler)
    try:
        bpy.utils.unregister_class(VSEQuickFunctionSettings)
    except RuntimeError:
        pass

    #Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
