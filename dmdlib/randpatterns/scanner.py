from dmdlib.randpatterns.shared import *
# from dmdlib.randpatterns.sparsenoise import *

import numpy as np


@nb.jit()
def _select(arr, indexes, gap, npix):
    n, h, w = arr.shape
    for i in range(0, n, gap+1):
        picks = np.random.choice(indexes, npix, replace=False)
        frame = arr[i, :, :]
        frame.ravel()[picks] = True


def generate_scanner_seqs(seq_array_bool, seq_array, scale: int, debug=False, mask=None, npixels=1, gap_frames=0):
    """

    :param seq_array_bool: n x (dmd.h / scale) x (dmd.w / scale) array that is going to be scaled.
    :param seq_array: n x dmd.h, x dmd.w array that is going to be uploaded to dmd
    :param scale: logical pixels to physical pixel scaling factor. i.e. scale=4 means that the image is made up of
    homogeneous elements of 4x4 pixel squares.
    :param debug: NA
    :param mask: boolean mask of w, h = dmd.w, dmd.h . Everything that is 0 is forced to 0.
    :param npixels: number of pixels to present per presentation frame
    :param gap_frames: number of frames between presentation frame. Default 0, where every frame is a presentation frame.
    :return:
    """
    unmasked = find_unmasked_px(mask, scale)
    n_frames, h, w = seq_array_bool.shape
    # it's easiest to work in the flat representation of the pixels, as we can operate on single numbers instead \
    # of tuples of x, y
    unmasked_idxs_flat, = np.where(unmasked.ravel())
    seq_array_bool[:, :, :] = False  # reset the array
    # _select(seq_array_bool, unmasked_idxs_flat, gap_frames, npixels)
    for i in range(0, n_frames, gap_frames + 1):
        # for every frame pick npixel indices and make them true
        picks = np.random.choice(unmasked_idxs_flat, npixels, replace=False)
        frame = seq_array_bool[i, :, :]
        frame.ravel()[picks] = True
    # print(seq_array_bool.sum())
    # n, h_full, w_full = seq_array.shape
    # assert n == n_frames
    # assert h_full // scale == h
    # assert w_full // scale == w
    zoomer(seq_array_bool, scale, seq_array)
    seq_array[:] *= mask  # mask is 1 in areas we want to stimulate and 0 otherwise. This is faster than alternatives.
    return


def main():
    parser.description = 'Single spot stimulation generator.'
    parser.add_argument('--gapframes', type=int, default=0,
                        help='number of blank frames between each spot presentation')
    parser.add_argument('--npixels', type=int, default=1, help='number of pixels to display in each presentation frame')
    args = parser.parse_args()
    run_presentations(args.nframes, args.savefile, generate_scanner_seqs, file_overwrite=args.overwrite, seq_debug=False,
                      picture_time=args.pic_time, mask_filepath=args.maskfile, image_scale=args.scale, npixels=args.npixels,
                      gap_frames=args.gapframes)



if __name__ == '__main__':
    import os
    d = r'D:'
    pth = os.path.join(d, 'scanner_test.h5')

    # mskfile = os.path.join(d, 'mask.npy')
    mskfile = r"D:\patters\mouse_11113\sess_001\mask.npy"

    run_presentations(.7 * 10 ** 6, pth, generate_scanner_seqs, file_overwrite=False, seq_debug=False, picture_time=10 * 1000,
                      mask_filepath=mskfile, npixels=1, gap_frames=50)
