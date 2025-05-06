#originals found at https://github.com/blender/blender/blob/main/scripts/startup/bl_ui/space_sequencer.py

import bpy
from bpy.types import Menu
from bpy.app.translations import (
    contexts as i18n_contexts,
    pgettext_rpt as rpt_,
)

def _space_view_types(st):
    view_type = st.view_type
    return (
        view_type in {'SEQUENCER', 'SEQUENCER_PREVIEW'},
        view_type == 'PREVIEW',
    )


def selected_strips_count(context):
    selected_strips = getattr(context, "selected_strips", None)
    if selected_strips is None:
        return 0, 0

    total_count = len(selected_strips)
    nonsound_count = sum(1 for strip in selected_strips if strip.type != 'SOUND')

    return total_count, nonsound_count


class SEQUENCER_MT_add(Menu):
    bl_label = "Add"
    bl_translation_context = i18n_contexts.operator_default
    bl_options = {'SEARCH_ON_KEY_PRESS'}

    def draw(self, context):

        layout = self.layout
        layout.operator_context = 'INVOKE_REGION_WIN'

        layout.menu("SEQUENCER_MT_add_scene", text="Scene", icon='SCENE_DATA')

        bpy_data_movieclips_len = len(bpy.data.movieclips)
        if bpy_data_movieclips_len > 10:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("sequencer.movieclip_strip_add", text="Clip...", icon='TRACKER')
        elif bpy_data_movieclips_len > 0:
            layout.operator_menu_enum("sequencer.movieclip_strip_add", "clip", text="Clip", icon='TRACKER')
        else:
            layout.menu("SEQUENCER_MT_add_empty", text="Clip", text_ctxt=i18n_contexts.id_movieclip, icon='TRACKER')
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

        total, nonsound = selected_strips_count(context)

        col = layout.column()
        col.menu("SEQUENCER_MT_add_transitions", icon='ARROW_LEFTRIGHT')
        # Enable for video transitions or sound cross-fade.
        col.enabled = nonsound == 2 or (nonsound == 0 and total == 2)

        col = layout.column()
        col.operator_menu_enum("sequencer.fades_add", "type", text="Fade", icon='IPO_EASE_IN_OUT')
        col.enabled = total >= 1


class SEQUENCER_MT_strip_transform(Menu):
    bl_label = "Transform"

    def draw(self, context):
        layout = self.layout
        st = context.space_data
        has_sequencer, has_preview = _space_view_types(st)

        if has_preview:
            layout.operator_context = 'INVOKE_REGION_PREVIEW'
        else:
            layout.operator_context = 'INVOKE_REGION_WIN'

        if has_preview:
            layout.operator("transform.translate", text="Move")
            layout.operator("transform.rotate", text="Rotate")
            layout.operator("transform.resize", text="Scale")
        else:
            #layout.operator("transform.seq_slide", text="Move").view2d_edge_pan = True
            #layout.operator("transform.transform", text="Move/Extend from Current Frame").mode = 'TIME_EXTEND'
            #layout.operator("sequencer.slip", text="Slip Strip Contents")
            layout.operator("vseqf.grab", text="Grab/Move")
            layout.operator("vseqf.grab", text="Move/Extend from Current Frame").mode = 'TIME_EXTEND'
            layout.operator("vseqf.grab", text="Slip Strip Contents").mode = 'SLIP'

        # TODO (for preview)
        if has_sequencer:
            layout.separator()
            #layout.operator("sequencer.snap")
            layout.operator("sequencer.offset_clear")

            layout.separator()

        if has_sequencer:
            layout.operator_menu_enum("sequencer.swap", "side")

            layout.separator()
            layout.operator("sequencer.gap_remove").all = False
            layout.operator("sequencer.gap_remove", text="Remove Gaps (All)").all = True
            layout.operator("sequencer.gap_insert")

        layout.separator()
        layout.operator('vseqf.quicksnaps', text='Snap Beginning To Cursor').type = 'begin_to_cursor'
        layout.operator('vseqf.quicksnaps', text='Snap End To Cursor').type = 'end_to_cursor'
        layout.operator('vseqf.quicksnaps', text='Snap To Previous Strip').type = 'strip_to_previous'
        layout.operator('vseqf.quicksnaps', text='Snap To Next Strip').type = 'strip_to_next'


class SEQUENCER_MT_strip(Menu):
    bl_label = "Strip"

    def draw(self, context):
        from bl_ui_utils.layout import operator_context

        layout = self.layout
        st = context.space_data
        has_sequencer, has_preview = _space_view_types(st)

        layout.menu("SEQUENCER_MT_strip_transform")

        if has_preview:
            layout.operator_context = 'INVOKE_REGION_PREVIEW'
        else:
            layout.operator_context = 'INVOKE_REGION_WIN'

        strip = context.active_strip

        if has_preview:
            layout.separator()
            layout.operator("sequencer.preview_duplicate_move", text="Duplicate")
            layout.separator()
            layout.menu("SEQUENCER_MT_strip_show_hide")
            layout.separator()
            if strip and strip.type == 'TEXT':
                layout.menu("SEQUENCER_MT_strip_text")

        if has_sequencer:
            layout.menu("SEQUENCER_MT_strip_retiming")
            layout.separator()

            with operator_context(layout, 'EXEC_REGION_WIN'):
                #props = layout.operator("sequencer.split", text="Split")
                #props.type = 'SOFT'
                layout.operator("vseqf.cut", text="Cut/Split").type = 'SOFT'

                #props = layout.operator("sequencer.split", text="Hold Split")
                #props.type = 'HARD'
                layout.operator("vseqf.cut", text="Hold Cut/Split").type = 'HARD'

            layout.separator()

            layout.operator("sequencer.copy", text="Copy")
            layout.operator("sequencer.paste", text="Paste")
            layout.operator("sequencer.duplicate_move", text="Duplicate")

        layout.separator()
        layout.operator("sequencer.delete", text="Delete")

        if strip and strip.type == 'SCENE':
            layout.operator("sequencer.delete", text="Delete Strip & Data").delete_data = True
            layout.operator("sequencer.scene_frame_range_update")

        if has_sequencer:
            if strip:
                strip_type = strip.type
                layout.separator()
                layout.operator_menu_enum("sequencer.strip_modifier_add", "type", text="Add Modifier")
                layout.operator("sequencer.strip_modifier_copy", text="Copy Modifiers to Selection")

                if strip_type in {
                        'CROSS', 'ADD', 'SUBTRACT', 'ALPHA_OVER', 'ALPHA_UNDER',
                        'GAMMA_CROSS', 'MULTIPLY', 'WIPE', 'GLOW',
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
                    layout.operator("sequencer.meta_make")
                    layout.operator("sequencer.meta_separate")
                    layout.operator("sequencer.meta_toggle", text="Toggle Meta")
                if strip_type != 'META':
                    layout.separator()
                    layout.operator("sequencer.meta_make")
                    layout.operator("sequencer.meta_toggle", text="Toggle Meta")

        if has_sequencer:
            layout.separator()
            layout.menu("SEQUENCER_MT_color_tag_picker")

            layout.separator()
            layout.menu("SEQUENCER_MT_strip_lock_mute")

            layout.separator()
            layout.operator("sequencer.connect", icon='LINKED').toggle = True
            layout.operator("sequencer.disconnect")

            layout.separator()
            layout.menu("SEQUENCER_MT_strip_input")
