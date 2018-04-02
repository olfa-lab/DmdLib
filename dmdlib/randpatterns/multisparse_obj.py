import numba as nb
import numpy as np
from dmdlib.core.ALP import AlpDmd
from dmdlib.randpatterns import utils
from dmdlib.randpatterns import ephys_comms
import os
from dmdlib.randpatterns import saving
from dmdlib.randpatterns.presenter import Presenter
if os.name == 'nt':
    appdataroot = os.environ['APPDATA']
    appdatapath = os.path.join(appdataroot, 'dmdlib')


class MultiSparse:
    """
    Stimulus generator for sparse random patterns drawn from varying probability distributions.
    """
    def __init__(self, probabilities, switch_frequency, mask=None, scale=1):
        self.random_probs = np.array(probabilities)
        self.switch_frequency = int(switch_frequency)
        self._frame_count = 0  # saves state
        self.scale = scale
        self._last_p = -1.
        if mask is not None:
            self.mask = mask
            self.unmasked = utils.find_unmasked_px(mask, scale)
            self.n_unmasked_pix = self.unmasked.sum()

    def make_patterns(self, boolean_array: np.ndarray, whole_seq_array: np.ndarray, debug):
        """
        Modifies arrays in place with random values (on, off).

        This makes sparse random patterns drawn from varying probability distributions.

        :param boolean_array: boolean array that is of shape ( n_frames, h / scale, w / scale)
        :param whole_seq_array: array of uint8 values of shave (n_frames, h, w)
        :param debug: not implemented.
        """

        n_frames, h, w = boolean_array.shape
        total_randnums = n_frames * self.n_unmasked_pix

        probs = np.zeros(total_randnums)
        self._frame_count = self._gen_probs(probs, self._frame_count, self.n_unmasked_pix, self.switch_frequency,
                                            self.random_probs, self._last_p)
        self._last_p = probs[-1]  # save this for the next iteration if we're in the middle of a presentation block.
        a = np.random.binomial(1, probs, total_randnums)
        utils.reshape(a, self.unmasked, boolean_array)
        utils.zoomer(boolean_array, self.scale, whole_seq_array)
        whole_seq_array *= self.mask

    @staticmethod
    @nb.jit
    def _gen_probs(array, frame_count, px_per_frame, switch_freq, probabilities, last_p) -> int:
        """
        Generates an array of probabilities for input to the binomial.

        Returns the updated frame count: framecount + pixels_generated // pixels_per frame.
        Note that this lags by 1, because 0%anything is True, so it is iterated at the beginning of the next generation
        cycle.

        :param array: array to modify (in place)
        :param frame_count: current number of frames that have been presented.
        :param px_per_frame: number of pixels per frame (for defining stride)
        :param switch_freq: number of frames prior to switching probabilities.
        :param probabilities:
        :param last_p:
        :return:
        """

        n_probs = len(probabilities)
        current_p = last_p  # this will be updated when necessary.

        for i_px in range(array.shape[0]):
            if not i_px % px_per_frame:  # moving to the next frame.
                if not frame_count % switch_freq:
                    current_p = probabilities[np.random.randint(0, n_probs)]
                frame_count += 1
            array[i_px] = current_p
        return frame_count


def main():
    parser = utils.setup_parser()
    parser.description = 'Sparsenoise stimulus generator.'
    parser.add_argument('fraction_on', type=float, nargs='*',
                        help='fraction of pixels on per presentation frame (between 0 and 1)')
    parser.add_argument('--switch_freq', type=int, default=500,
                        help='number of frames between switching stimulus probabilities.')
    args = parser.parse_args()
    frac = args.fraction_on

    if any([x > 1. or x < 0. for x in frac]):
        errst = 'Fraction arguments must be between 0 and 1.'
        raise ValueError(errst)

    fullpath = os.path.abspath(args.savefile)
    if not args.overwrite and os.path.exists(args.savefile):
        errst = "{} already exists.".format(fullpath)
        raise FileExistsError(errst)

    mask = np.load(args.maskfile)
    generator = MultiSparse(frac, args.switch_freq, mask, args.scale)

    presentations_per = min([60000, args.nframes])

    n_runs = int(np.ceil(args.nframes / presentations_per))
    assert n_runs > 0
    with saving.HfiveSaver(fullpath, args.overwrite) as saver, AlpDmd() as dmd:
        saver.store_mask_array(mask)
        uuid = saver.uuid
        if not args.no_phys:
            ephys_comms.record_start(uuid, fullpath)
        run_id = saver.current_group_id
        for i in range(n_runs):
            print("Starting presentation run {} of {} ({}).".format(i + 1, n_runs, run_id))
            if not args.no_phys:
                ephys_comms.record_presentation(run_id)
            presenter = Presenter(dmd, generator, saver, presentations_per, image_scale=args.scale,
                                  picture_time=args.pic_time, )
            presenter.run()
            run_id = saver.iter_pattern_group()



