# import numba as nb
import numpy as np
from dmdlib.randpatterns.utils import run_presentations, zoomer, find_unmasked_px, reshape
import os
if os.name == 'nt':
    appdataroot = os.environ['APPDATA']
    appdatapath = os.path.join(appdataroot, 'dmdlib')





def sparsenoise_function_generator(random_threshold):

    def sequence_generator(seq_array_bool, seq_array, scale: int, debug=False, mask=None):
        """ Generates a sequence for upload to DMD.

        :param seq_array_bool: boolean ndarray to write the random bits, dimensions (N_pix, H_dmd/scale, W_dmd/scale)
        :param seq_array: uint8 ndarray for upload with dimensions (N_pix, H_dmd, W_dmd)
        :param scale: scale for discreet random pixels in DMD space. ie if scale=2, each random pixel will be
        projected as 2x2 pix on the dmd.
        :param debug: use numeric debug sequence generator to test synchronization.
        """
        if random_threshold is None:
            raise ValueError('random_threshold kwarg is not set.')

        unmasked = find_unmasked_px(mask, scale)
        n_nmasked = unmasked.sum()
        n_frames, h, w = seq_array_bool.shape

        total_randnums = n_nmasked * n_frames
        randnums = np.random.rand(total_randnums)
        randbool = randnums <= random_threshold
        reshape(randbool, unmasked, seq_array_bool)
        zoomer(seq_array_bool, scale, seq_array)
        seq_array[:] *= mask  # mask is 1 in areas we want to stimulate and 0 otherwise. This is faster than alternatives.
    return sequence_generator


def main():
    parser.description = 'Sparsenoise stimulus generator.'
    parser.add_argument('fraction_on', type=float,
                        help='fraction of pixels on per presentation frame (between 0 and 1)')
    args = parser.parse_args()
    frac = args.fraction_on
    if frac > 1. or frac < 0.:
        errst = 'Fraction argument must be between 0 and 1.'
        raise ValueError(errst)
    else:
        generate_sparsenoise_sequences = sparsenoise_function_generator(frac)
        run_presentations(args.nframes, args.savefile, generate_sparsenoise_sequences, file_overwrite=args.overwrite,
                          seq_debug=False, image_scale=args.scale, picture_time=args.pic_time, mask_filepath=args.maskfile)


if __name__ == '__main__':
    import os
    d = r"D:"
    pth = os.path.join(d, 'test.h5')
    # mskfile = os.path.join(d, 'mask.npy')
    mskfile = r"D:\patters\mouse_11113\sess_001\mask.npy"
    if os.path.exists(d) and os.path.exists(mskfile) and not os.path.exists(pth):
        generate_sparsenoise_sequences = sparsenoise_function_generator(.005)
        run_presentations(.7 * 10 ** 6, pth, file_overwrite=False, seq_debug=False, picture_time=10 * 1000,
                          mask_filepath=mskfile)
    elif not os.path.exists(mskfile):
        raise FileNotFoundError('Mask file not found ({})'.format(mskfile))
    elif os.path.exists(pth):
        raise FileExistsError("Patterns file already exists {}.".format(pth))