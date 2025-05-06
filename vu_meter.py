import bpy
import math
from . import vseqf
from . import fades
from . import timeline

vu_max_delay = 0
vu_meter_min = -60
vu_meter_sweet_spot = 0.7


def display_report(report):
    text_document = None
    for text in bpy.data.texts:
        if text.name == 'Clipping Report':
            text_document = text
            break
    if text_document is None:
        text_document = bpy.data.texts.new('Clipping Report')
    text_document.clear()
    text_document.from_string(report)


def get_volume_unit(frame=None):
    total = 0
    if bpy.context.scene.sequence_editor is None:
        return 0
    sequence_editor = bpy.context.scene.sequence_editor
    strips = sequence_editor.strips_all
    depsgraph = bpy.context.evaluated_depsgraph_get()
    if frame is None:
        frame = bpy.context.scene.frame_current
        evaluate_volume = False
    else:
        evaluate_volume = True
    fps = vseqf.get_fps()
    for strip in strips:
        if strip.type == 'SOUND' and timeline.under_cursor(strip, frame) and not timeline.is_muted(sequence_editor, strip):
            time_from = (frame - 1 - strip.frame_start) / fps
            time_to = (frame - strip.frame_start) / fps
            audio = strip.sound.evaluated_get(depsgraph).factory
            chunk = audio.limit(time_from, time_to).data()
            if len(chunk) == 0:
                #sometimes the chunks cannot be read properly, try to read 2 frames instead
                time_from_temp = (frame - 2 - strip.frame_start) / fps
                chunk = audio.limit(time_from_temp, time_to).data()
            if len(chunk) == 0:
                #chunk still couldnt be read... just give up :\
                average = 0
            else:
                max = abs(chunk.max())
                min = abs(chunk.min())
                if max > min:
                    average = max
                else:
                    average = min
            if evaluate_volume:
                fcurve = fades.get_fade_curve(bpy.context, strip, create=False)
                if fcurve:
                    volume = fcurve.evaluate(frame)
                else:
                    volume = strip.volume
            else:
                volume = strip.volume
            total = total + (average * volume)
    return total


def vu_meter_calculate(scene):
    if scene != bpy.context.scene:
        return

    if not bpy.context.screen:
        return

    sequencers = []
    for area in bpy.context.screen.areas:
        if area.type == 'SEQUENCE_EDITOR':
            sequencers.append(area)
    if not sequencers:
        return

    vseqf_settings = scene.vseqf
    if vseqf_settings.vu_show:
        percent_vu = get_volume_unit()
        vseqf_settings.vu = percent_to_db(percent_vu)
        global vu_max_delay
        vu_max_delay = vu_max_delay + 1
        if vseqf_settings.vu_max < vseqf_settings.vu or vu_max_delay > 30:
            vseqf_settings.vu_max = vseqf_settings.vu
            vu_max_delay = 0

        # make sure sequence editor is refreshed on blender 3.x
        for area in sequencers:
            area.tag_redraw()


def percent_to_db(percent):
    if percent == 0:
        db = vu_meter_min
    else:
        db = 20 * math.log10(percent)
        if db < vu_meter_min:
            db = vu_meter_min
    return db


def vu_formatted(db):
    if db <= vu_meter_min:
        db_text = '-inf db'
    else:
        db_text = format(db, '.2f')+'db'
    return db_text.rjust(8)


def vu_meter_draw():
    context = bpy.context
    vseqf_settings = context.scene.vseqf
    if vseqf_settings.vu_show:
        offset_x = 15
        scrollbar = 15
        bottom_section = 40
        top_section = 20

        text_color = [1, 1, 1, 1]
        warn_color = [1, .0, .0, 1]
        very_high_color = [1, .6, .6, 1]
        high_color = [1, 1, .5, 1]
        bg_color = [0, 0, 0, 1]
        region = context.region
        max_height = region.height - top_section
        meter_height = max_height - bottom_section

        #Draw Background
        vseqf.draw_rect(offset_x, scrollbar, 45, max_height - scrollbar, bg_color)
        marks = [
            [1,     '____    '], 
            [.9,    '____ -6 '], 
            [.7,    '____ -18'], 
            [.3333, '____ -40'], 
            [0,     '____ -60']
        ]
        for mark in marks:
            height = 1 + bottom_section + (mark[0] * meter_height)
            vseqf.draw_text(offset_x, height, 10, mark[1], color=(.5, .5, .5, 1))
        vu = vseqf_settings.vu
        if vu > 0:
            vu = 0
            vu_color = warn_color
        else:
            vu_color = text_color
        vu_percent = ((vu + -vu_meter_min)/-vu_meter_min)
        vu_size = meter_height * vu_percent

        #Draw meter
        vseqf.draw_rect(offset_x + 2, bottom_section, 15, vu_size, vu_color)
        if 0 >= vseqf_settings.vu > -18:
            high_start = 0.7 * meter_height
            high_size = vu_size - high_start
            vseqf.draw_rect(offset_x + 2, bottom_section + high_start, 15, high_size, high_color)
            if vseqf_settings.vu > -6:
                warn_start = 0.9 * meter_height
                warn_size = vu_size - warn_start
                vseqf.draw_rect(offset_x + 2, bottom_section + warn_start, 15, warn_size, very_high_color)

        vseqf.draw_text(offset_x, 20, 10, vu_formatted(vseqf_settings.vu), color=vu_color)

        vu_max = vseqf_settings.vu_max
        if vu_max > 0:
            vu_max = 0
            vu_max_color = warn_color
        elif vu_max > -6:
            vu_max_color = very_high_color
        elif vu_max > -18:
            vu_max_color = high_color
        else:
            vu_max_color = text_color
        vu_max_percent = ((vu_max + -vu_meter_min)/-vu_meter_min)
        vu_max_pos = meter_height * vu_max_percent
        vseqf.draw_rect(offset_x + 2, bottom_section + vu_max_pos - 2, 15, 2, vu_max_color)


class VUMeterCheckClipping(bpy.types.Operator):
    bl_idname = 'vseqf.check_clipping'
    bl_label = 'Check For Audio Clipping'

    start = 0
    end = 0
    current = 0
    percentage = 0
    clipping = []

    def execute(self, context):
        self.percentage = 0
        scene = context.scene
        self.start = scene.frame_start
        self.end = scene.frame_end
        self.current = self.start
        self._timer = context.window_manager.event_timer_add(time_step=0.00001, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.window_manager.progress_begin(0, 100)
        self.clipping = []
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.end_modal(context)
            return {'CANCELLED'}
        volume = get_volume_unit(self.current)
        self.percentage = (self.current - self.start) / (self.end - self.start)
        context.window_manager.progress_update(self.percentage)
        if volume > 1:
            self.clipping.append([self.current, volume])
        self.current = self.current + 1
        if self.current > self.end:
            self.end_modal(context)
            if len(self.clipping) > 0:
                clipped_report = 'Found '+str(len(self.clipping))+' frames with audio clipping:\n\n'
                for clipped in self.clipping:
                    clipped_report = clipped_report+'Frame '+str(clipped[0])+' clipping at volume '+str(clipped[1])+'\n'
            else:
                clipped_report = 'No clipping found'
            self.report({'INFO'}, "Clipping report saved, check 'Clipping Report' in the text editor")
            display_report(clipped_report)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def end_modal(self, context):
        context.window_manager.progress_end()
        context.window_manager.event_timer_remove(self._timer)
