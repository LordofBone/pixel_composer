import string
from time import time
import logging
import itertools
from .shaders import FullScreenPatternShader, PerPixelLightingShader, MotionBlurShader, \
    FullScreenGradientShader, \
    FloatToRGBShader, ShaderStack, ToneMapShader, SpriteShader

logger = logging.getLogger("rasterizer-logger")

"""
WARNING: be careful with this, it can cause flashing images
"""
def timer(func):
    def wrapper(*arg_in, **kw):
        st = time()
        out = func(*arg_in, **kw)
        et = time()

        elapsed_time = et - st
        if elapsed_time > 0.0:
            print(f'{func} Execution time:', elapsed_time, 'seconds')
        return out

    return wrapper

class FrameBuffer:
    def __init__(self, session_info):
        self.session_info = session_info

        self.front_buffer = {}
        self.back_buffer = {}

        self.texture_plane = {}

        self.render_plane = {}

        self.previous_frame = {}

        self.blank_pixel = (0.0, 0.0, 0.0)

        self.current_buffer_front = True

        self.motion_blur = MotionBlurShader()

        self.lighting = PerPixelLightingShader()

        self.tone_map = ToneMapShader()

        self.float_to_rgb = FloatToRGBShader()

        self.shader_stack = ShaderStack(self.session_info)

        self.sprites = SpriteShader()

    def log_current_frame(self):
        self.previous_frame = self.render_plane.copy()

    def return_previous_frame(self):
        return self.previous_frame.copy()

    def write_to_render_plane(self, pixel_coord, pixel_rgb):
        self.render_plane[pixel_coord] = pixel_rgb

    def write_to_previous_frame(self, pixel_coord, pixel_rgb):
        self.previous_frame[pixel_coord] = pixel_rgb

    def get_from_render_plane(self, pixel_coord):
        try:
            pixel_rgb = self.render_plane[pixel_coord]
            return pixel_rgb
        except KeyError:
            return self.blank_pixel

    def blit_render_plane_to_buffer(self):
        if self.current_buffer_front:
            self.front_buffer = self.render_plane.copy()
        else:
            self.back_buffer = self.render_plane.copy()

    def render_render_plane_to_buffer(self):
        [self.write_to_buffer(coord, self.get_from_render_plane(coord)) for coord in self.session_info.coord_map]

    def write_to_buffer(self, pixel_coord, pixel_rgb):
        if self.current_buffer_front:
            self.front_buffer[pixel_coord] = pixel_rgb
        else:
            self.back_buffer[pixel_coord] = pixel_rgb

    def return_buffer(self):
        if self.current_buffer_front:
            return self.front_buffer
        else:
            return self.back_buffer

    def get_from_buffer(self, pixel_coord):
        try:
            if self.current_buffer_front:
                pixel_rgb = self.front_buffer[pixel_coord]
            else:
                pixel_rgb = self.back_buffer[pixel_coord]

            return pixel_rgb
        except KeyError:
            return None

    def flip_buffers(self):
        self.current_buffer_front = not self.current_buffer_front

    def flush_buffer(self):
        self.render_plane = {}

        self.texture_plane = {}

        if self.current_buffer_front:
            self.front_buffer = {}
        else:
            self.back_buffer = {}

    def write_to_texture(self, pixel_coord, pixel_rgb):
        if self.current_buffer_front:
            self.texture_plane[pixel_coord] = pixel_rgb

    def write_texture_to_buffer(self, coord, texture):
        try:
            for pixel_coord, texel in texture.items():
                # print(f'Pixel Coord: {pixel_coord}, Texel: {texel}')
                self.write_to_texture(pixel_coord, texel)
        except TypeError:
            pass
        except AttributeError:
            pass


class ScreenDrawer:
    def __init__(self, output_controller, buffer_refresh, session_info, world_space, exit_text="Program Exited"):
        self.session_info = session_info
        self.world_space_access = world_space
        self.output_controller = output_controller
        self.frame_refresh_delay_ms = 1 / buffer_refresh
        logger.debug(f'Milliseconds per-frame to aim for: {self.frame_refresh_delay_ms}')

        self.frame_buffer_access = FrameBuffer(self.session_info)

        self.next_frame = time() + self.frame_refresh_delay_ms

        self.exit_text = exit_text

        # you can get some different/cool effects by swapping things about here
        self.render_stack = ['background_shader_pass',
                             'object_colour_pass',
                             'log_current_frame',
                             'tone_map_pass',
                             'render_frame_buffer',
                             'float_to_rgb_pass',
                             'buffer_scan',
                             'flush_buffer']

    def sprite_pass(self):
        [self.frame_buffer_access.write_texture_to_buffer(coord, self.frame_buffer_access.sprites.run_shader(coord,
                                                                                                             pixel))
         for coord, pixel in self.frame_buffer_access.front_buffer.items()]

    def write_texture(self):
        [self.frame_buffer_access.write_to_buffer(coord, pixel)
         for coord, pixel in self.frame_buffer_access.texture_plane.items()]

    def float_to_rgb_pass(self):
        [self.frame_buffer_access.write_to_buffer(coord, self.frame_buffer_access.float_to_rgb.run_shader(pixel)) for
         coord, pixel in
         self.frame_buffer_access.front_buffer.items()]

    def object_colour_pass(self):
        # [self.frame_buffer_access.write_to_render_plane(coord, pixel) for coord, pixel in
        #  self.world_space_access.return_world_space().items()]
        # items_list = list(self.world_space_access.return_world_space().items())

        # [self.frame_buffer_access.write_to_render_plane(coord, pixel) for coord, pixel in list(self.world_space_access.return_world_space().items())[::1]]

        new_dict = dict(list(self.world_space_access.return_world_space().items())[::16])
        [self.frame_buffer_access.write_to_render_plane(coord, pixel) for coord, pixel in
         new_dict.items()]

        # items = self.world_space_access.return_world_space().items()
        # step = 64
        # start = 0
        # selected_items = itertools.islice(items, start, None, step)

        # [self.frame_buffer_access.write_to_render_plane(coord, pixel) for coord, pixel in selected_items]

    def background_shader_pass(self):
        [self.frame_buffer_access.write_to_render_plane(coord, self.frame_buffer_access.shader_stack.run_shader_stack(
            self.frame_buffer_access.get_from_render_plane(coord)))
         for coord in
         self.session_info.coord_map]
    # @timer
    def lighting_pass(self):
        [self.frame_buffer_access.write_to_render_plane(coord,
                                                        self.frame_buffer_access.lighting.run_shader(coord, pixel))
         for coord, pixel in self.frame_buffer_access.render_plane.items()]

    def tone_map_pass(self):
        [self.frame_buffer_access.write_to_render_plane(coord, self.frame_buffer_access.tone_map.run_shader(pixel))
         for coord, pixel in self.frame_buffer_access.render_plane.items()]

    def buffer_scan(self):
        [self.draw_to_output(coord, pixel) for coord, pixel in self.frame_buffer_access.return_buffer().items()]

        self.output_controller.show()

    def buffer_flip(self):
        self.frame_buffer_access.flip_buffers()

    def log_current_frame(self):
        self.frame_buffer_access.log_current_frame()
    def blit_render_plane(self):
        self.frame_buffer_access.blit_render_plane_to_buffer()

    def render_frame_buffer(self):
        self.frame_buffer_access.render_render_plane_to_buffer()

    def draw_to_output(self, coord, pixel):
        self.output_controller.draw_pixels(coord, pixel)

    def motion_blur_pass(self):
        # todo: convert this to list comprehension? and tidy it up
        for coord, pixel in self.frame_buffer_access.return_previous_frame().items():
            try:
                new_pixel = self.frame_buffer_access.motion_blur.run_shader(pixel,
                                                                            self.frame_buffer_access.render_plane[
                                                                                coord])
            except KeyError:
                new_pixel = self.frame_buffer_access.motion_blur.run_shader(pixel)
            if new_pixel:
                self.frame_buffer_access.write_to_render_plane(coord, new_pixel)

    def lensing_pass(self):
        # todo: convert this to list comprehension
        # this is similar function to motion blur but it results in some
        # weird/cool effects when implemented after background and lighting passes, causes the background to react
        # to the lighting
        for coord, pixel in self.frame_buffer_access.return_previous_frame().items():
            new_pixel = self.frame_buffer_access.motion_blur.run_shader(pixel)
            if new_pixel:
                self.frame_buffer_access.write_to_render_plane(coord, new_pixel)

    def flush_buffer(self):
        self.frame_buffer_access.flush_buffer()
    @timer
    def draw(self):
        try:
            for i in (range(8192)):
            # while True:
                if self.session_info.rendering_on:
                    [getattr(self, render_stage)() for render_stage in self.render_stack]

                    if time() > self.next_frame:
                        # todo: do something clever with buffer flipping here?
                        pass
        # this is here so that if this is called as a thread it can be exited by passing in {"end": "ended"} into the
        # world space dict from the main program, else if nonsense is passed in it will raise an error
        except TypeError as e:
            if next(iter(self.world_space_access.return_world_space())) == "end":
                logger.info("Render thread purposely ended")
                quit()
            else:
                logger.error(f"Type Error: {e}")
                raise e
        # upon keyboard interrupt display information about the program run before exiting
        except KeyboardInterrupt:
            logger.info(logger.info(string.Template(self.exit_text).substitute(vars(self.session_info))))
            self.frame_buffer_access.flush_buffer()
            self.buffer_scan()
