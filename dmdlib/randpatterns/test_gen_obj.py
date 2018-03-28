"""
Object to test Presenter/Saver for synchronization and sequential presentation of images as expected by presenting
digits in order.
"""
from __future__ import division
from PIL import ImageFont
import numpy as np
import numba
from dmdlib.randpatterns import utils
from dmdlib.randpatterns import saving
from dmdlib.randpatterns.presenter import Presenter
from dmdlib.core.ALP import AlpDmd
import os

font = ImageFont.load_default()


class TestGenerator:

    def __init__(self, mask=None, scale=1):
        self.scale = scale
        self.mask = mask
        self._count = 0

    def make_patterns(self, boolean_array, whole_seq_array, debug):

        n_frames, h, w = boolean_array.shape
        _, h_full, w_full = whole_seq_array.shape
        assert h_full // h == self.scale
        # whole_seq_array[:, :, :] = 0
        boolean_array[:, :, :] = False
        for i in range(n_frames):
            msg = '{:06n}'.format(self._count)
            # self._make_text_fast(msg, whole_seq_array[i, :, :])

            self._make_text_fast(msg, boolean_array[i, :, :], margins=(2, 2, 37, 37))
            self._count += 1

        utils.zoomer(boolean_array, self.scale, whole_seq_array)

    def _make_text_fast(self, text, array, margins=(10, 10, 150, 150)):
        mask = font.getmask(text)
        txt_mask_array = np.asarray(mask, dtype=bool)
        height, width = array.shape
        txt_mask_array.shape = mask.size[1], mask.size[0]
        left, right, top, bottom,  = margins
        self._array_maker(array, txt_mask_array, top, bottom, left, right, width, height)

        return

    @staticmethod
    @numba.jit(nopython=True, parallel=True)
    def _array_maker(arrayout, arrayin, top, bottom, left, right, width, height):
        """
        Produces a scaled translation of array within arrayout.

        :param arrayout:
        :param arrayin:
        :param top:
        :param bottom:
        :param left:
        :param right:
        :param width:
        :param height:
        :return:
        """
        W_margins = width - right - left
        H_margins = height - top - bottom
        mH, mW = arrayin.shape
        W_scale = int(np.ceil(W_margins / mW))
        H_scale = int(np.ceil(H_margins / mH))
        # print(arrayout.shape)
        # print(W_margins )
        for x in range(W_margins):
            x_mask = x // W_scale
            for y in range(H_margins):
                y_mask = y // H_scale
                maskv = arrayin[y_mask, x_mask]
                if maskv:
                    arrayout[y+top, x+left] = True
        return


def main():
    parser = utils.setup_parser()
    parser.description = 'Sparsenoise stimulus generator.'
    args = parser.parse_args()

    fullpath = os.path.abspath(args.savefile)
    if not args.overwrite and os.path.exists(args.savefile):
        errst = "{} already exists.".format(fullpath)
        raise FileExistsError(errst)

    # mask = np.load(args.maskfile)
    mask = None
    generator = TestGenerator(mask, args.scale)

    presentations_per = min([args.frames_per_run, args.nframes])

    n_runs = int(np.ceil(args.nframes / presentations_per))
    assert n_runs > 0
    with saving.HfiveSaver(fullpath, args.overwrite) as saver, AlpDmd() as dmd:
        # saver.store_mask_array(mask)
        uuid = saver.uuid
        # ephys_comms.record_start(uuid, fullpath)
        run_id = saver.current_group_id
        for i in range(n_runs):
            print("Starting presentation run {} of {} ({}).".format(i + 1, n_runs, run_id))
            # ephys_comms.record_presentation(run_id)
            presenter = Presenter(dmd, generator, saver, presentations_per, scale=args.scale,
                                  picture_time=args.pic_time, )
            presenter.run()
            run_id = saver.iter_pattern_group()

if __name__ == '__main__':
    main()
