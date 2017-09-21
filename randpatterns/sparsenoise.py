from shared import main, presenter
import test_imgen
from ctypes import *
import numba as nb
import numpy as np
import random
from shared import main, zoomer


@nb.jit(parallel=True)
def find_unmasked_px(mask, scale):
    """
    Find the (scaled) pixels that are not masked.
    :param mask:
    :param scale:
    :return:
    """
    h, w = mask.shape
    h_scaled = h // scale
    w_scaled = w // scale
    valid_array = np.zeros((h_scaled, w_scaled), dtype=bool)
    for y in nb.prange(h_scaled):
        st_y = y * scale
        nd_y = st_y + scale
        for x in range(w_scaled):
            st_x = x * scale
            nd_x = st_x + scale
            if np.any(mask[st_y:nd_y, st_x:nd_x]):
                valid_array[y, x] = True
    return valid_array


# @nb.jit  # numba 0.35.0 doesn't help here at all with fancy indexing
def reshape(random_unshaped_array, valid_array, seq_array_bool):
    """ Reshapes a random bool array into the correct shape. Modifies seq_array_bool in place.

    :param random_unshaped_array:
    :param valid_array: boolean 2d array describing where the random values in random_unshaped_array should be placed.
    :param seq_array_bool: 3d array (nframes, h, w) with the shape of a (scaled) sequence to be uploaded.
    :return: none (in place modification of seq_array_bool)
    """

    n_frames, h, w = seq_array_bool.shape
    n_valid = valid_array.sum()
    st = 0
    nd = n_valid
    for i in nb.prange(n_frames):
        fr = seq_array_bool[i]
        fr[valid_array] = random_unshaped_array[st:nd]
        st += n_valid
        nd += n_valid


def generate_sparsenoise_sequences(seq_array_bool, seq_array, scale: int, debug=False, mask=None, random_threshold=None):
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


if __name__ == '__main__':
    pth = r"D:\tester.h5"
    mskfile = r"D:\patters\mouse_11102\mask_right_bulb.npy"
    main(1 * 10 ** 6, pth, generate_sparsenoise_sequences, file_overwrite=True, seq_debug=False, picture_time=10 * 1000,
         mask_filepath=mskfile, random_threshold=.1)
