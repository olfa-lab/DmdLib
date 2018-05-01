# import numba as nb
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


class BiasedNoise:
    def __init__(self, bias_path,  mask=None,  scale=1):

        self.thresholds = np.load(bias_path)
        self.scale = scale
        if mask is not None:
            self.mask = mask
            self.unmasked = utils.find_unmasked_px(mask, scale)
            self.thresholds_flat = self.thresholds[self.unmasked]
            self.n_unmasked_pix = self.unmasked.sum()

    def make_patterns(self, boolean_array: np.ndarray, whole_seq_array: np.ndarray, debug):
        """
        Modifies arrays in place with random values (on, off).

        :param boolean_array: boolean array that is of shape ( n_frames, h / scale, w / scale)
        :param whole_seq_array: array of uint8 values of shave (n_frames, h, w)
        :param debug: not implemented.
        :return:
        """
        n_frames, h, w = boolean_array.shape
        total_randnums = n_frames * self.n_unmasked_pix
        randnums = np.random.rand(total_randnums)
        randbool = randnums <= self.thresholds_flat
        utils.reshape(randbool, self.unmasked, boolean_array)
        utils.zoomer(boolean_array, self.scale, whole_seq_array)
        whole_seq_array *= self.mask


def main():
    parser = utils.setup_parser()
    parser.description = 'Biase noise stimulus generator.'
    parser.add_argument('bias_array_path', type=str, help='Path to the bias npy file')
    parser.add_argument(
        'fraction_on', type=float,
        help='fraction of pixels on per presentation frame (between 0 and 1)'
    )
    args = parser.parse_args()

    frac = args.fraction_on
    if frac > 1. or frac < 0.:
        errst = 'Fraction argument must be between 0 and 1.'
        raise ValueError(errst)

    fullpath = os.path.abspath(args.savefile)
    if not args.overwrite and os.path.exists(args.savefile):
        errst = "{} already exists.".format(fullpath)
        raise FileExistsError(errst)

    mask = np.load(args.maskfile)

    generator = BiasedNoise(args.bias_array_path, mask,  args.scale)

    presentations_per = min([60000, args.nframes])

    if not args.no_phys:
        openephys = ephys_comms.OpenEphysComms()

    n_runs = int(np.ceil(args.nframes / presentations_per))
    assert n_runs > 0
    with saving.SparseSaver(fullpath, args.overwrite) as saver, AlpDmd() as dmd:
        saver.store_mask_array(mask)
        uuid = saver.uuid
        if not args.no_phys:
            openephys.record_start(uuid, fullpath)
        run_id = saver.current_group_id
        for i in range(n_runs):
            print("Starting presentation run {} of {} ({}).".format(i + 1, n_runs, run_id))
            if not args.no_phys:
                openephys.record_presentation(run_id)
            presenter = Presenter(dmd, generator, saver, presentations_per, image_scale=args.scale,
                                  picture_time=args.pic_time, )
            presenter.run()
            run_id = saver.iter_pattern_group()

if __name__ == '__main__':
    main()