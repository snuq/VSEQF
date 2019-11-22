import bpy
import gpu
import blf
import math
from gpu_extras.batch import batch_for_shader


class VSEQFTempSettings(object):
    """Substitute for the addon preferences when this script isn't loaded as an addon"""
    parenting = True
    fades = True
    proxy = True
    markers = True
    tags = True
    cuts = True
    edit = True
    threepoint = True


def add_to_value(value, character, is_float=True):
    if character in ['ZERO', 'NUMPAD_0']:
        value = value + '0'
    elif character in ['ONE', 'NUMPAD_1']:
        value = value + '1'
    elif character in ['TWO', 'NUMPAD_2']:
        value = value + '2'
    elif character in ['THREE', 'NUMPAD_3']:
        value = value + '3'
    elif character in ['FOUR', 'NUMPAD_4']:
        value = value + '4'
    elif character in ['FIVE', 'NUMPAD_5']:
        value = value + '5'
    elif character in ['SIX', 'NUMPAD_6']:
        value = value + '6'
    elif character in ['SEVEN', 'NUMPAD_7']:
        value = value + '7'
    elif character in ['EIGHT', 'NUMPAD_8']:
        value = value + '8'
    elif character in ['NINE', 'NUMPAD_9']:
        value = value + '9'
    elif character in ['PERIOD', 'NUMPAD_PERIOD']:
        if '.' not in value and is_float:
            value = value + '.'
    elif character in ['MINUS', 'NUMPAD_MINUS']:
        if '-' in value:
            value = value[1:]
        else:
            value = '-' + value
    elif character == 'BACK_SPACE':
        value = value[:-1]
    return value


#Drawing functions
def draw_line(sx, sy, ex, ey, color=(1.0, 1.0, 1.0, 1.0)):
    coords = [(sx, sy), (ex, ey)]
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {'pos': coords})
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_rect(x, y, w, h, color=(1.0, 1.0, 1.0, 1.0)):
    vertices = ((x, y), (x+w, y), (x, y+h), (x+w, y+h))
    indices = ((0, 1, 2), (2, 1, 3))
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_tri(v1, v2, v3, color=(1.0, 1.0, 1.0, 1.0)):
    vertices = (v1, v2, v3)
    indices = ((0, 1, 2), )
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_text(x, y, size, text, justify='left', color=(1.0, 1.0, 1.0, 1.0)):
    #Draws basic text at a given location
    font_id = 0
    blf.color(font_id, *color)
    if justify == 'right':
        text_width, text_height = blf.dimensions(font_id, text)
    else:
        text_width = 0
    blf.position(font_id, x - text_width, y, 0)
    blf.size(font_id, size, 72)
    blf.draw(font_id, text)


#Miscellaneous Functions
def get_prefs():
    if __name__ in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons[__name__].preferences
    else:
        prefs = VSEQFTempSettings()
    return prefs


def parenting():
    prefs = get_prefs()
    if prefs.parenting and bpy.context.scene.vseqf.children:
        return True
    else:
        return False


def proxy():
    prefs = get_prefs()
    if prefs.proxy and bpy.context.scene.vseqf.enable_proxy:
        return True
    else:
        return False


def redraw_sequencers():
    for area in bpy.context.screen.areas:
        if area.type == 'SEQUENCE_EDITOR':
            area.tag_redraw()


def apply_proxy_settings(seq):
    vseqf = bpy.context.scene.vseqf
    seq_type = seq.rna_type.name
    if seq_type in ['Movie Sequence', 'Image Sequence', 'MovieClip']:
        seq.use_proxy = True
        seq.proxy.build_25 = vseqf.proxy_25
        seq.proxy.build_50 = vseqf.proxy_50
        seq.proxy.build_75 = vseqf.proxy_75
        seq.proxy.build_100 = vseqf.proxy_100
        seq.proxy.quality = vseqf.proxy_quality
        return True
    return False


def get_fps(scene=None):
    if scene is None:
        scene = bpy.context.scene
    return scene.render.fps / scene.render.fps_base


def timecode_from_frames(frame, fps, levels=0, subsecond_type='miliseconds', mode='string'):
    """Converts a frame number to a standard timecode in the format: HH:MM:SS:FF
    Arguments:
        frame: Integer, frame number to convert to a timecode
        fps: Integer, number of frames per second if using 'frames' subsecond type
        levels: Integer, limits the number of timecode elements:
            1: returns: FF
            2: returns: SS:FF
            3: returns: MM:SS:FF
            4: returns: HH:MM:SS:FF
            0: returns an auto-cropped timecode with no zero elements
        subsecond_type: String, determines the format of the final element of the timecode:
            'miliseconds': subseconds will be divided by 100
            'frames': subseconds will be divvided by the current fps
        mode: return mode, if 'string', will return a string timecode, if other, will return a list of integers

    Returns: A string timecode"""

    #ensure the levels value is sane
    if levels > 4:
        levels = 4

    #set the sub second divisor type
    if subsecond_type == 'frames':
        subsecond_divisor = fps
    else:
        subsecond_divisor = 100

    #check for negative values
    if frame < 0:
        negative = True
        frame = abs(frame)
    else:
        negative = False

    #calculate divisions, starting at largest and taking the remainder of each to calculate the next smaller
    total_hours = math.modf(float(frame)/fps/60.0/60.0)
    total_minutes = math.modf(total_hours[0] * 60)
    remaining_seconds = math.modf(total_minutes[0] * 60)
    hours = int(total_hours[1])
    minutes = int(total_minutes[1])
    seconds = int(remaining_seconds[1])
    subseconds = int(round(remaining_seconds[0] * subsecond_divisor))

    if mode != 'string':
        return [hours, minutes, seconds, subseconds]
    else:
        hours_text = str(hours).zfill(2)
        minutes_text = str(minutes).zfill(2)
        seconds_text = str(seconds).zfill(2)
        subseconds_text = str(subseconds).zfill(2)

        #format and return the time value
        time_text = subseconds_text
        if levels > 1 or (levels == 0 and seconds > 0):
            time_text = seconds_text+'.'+time_text
        if levels > 2 or (levels == 0 and minutes > 0):
            time_text = minutes_text+':'+time_text
        if levels > 3 or (levels == 0 and hours > 0):
            time_text = hours_text+':'+time_text
        if negative:
            time_text = '-'+time_text
        return time_text
