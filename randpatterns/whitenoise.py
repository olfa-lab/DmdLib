import test_imgen
import numba as nb
import random
from shared import main, zoomer




_DEBUG_COUNTER = 0  # only used with debug routine to test sequentiality of images.


def number_sequence_generator(startnum, seq_array):
    """ Generate a sequence of numbers for testing sequentiality of sequence display.
    :param startnum: number to start from.
    :param seq_array:
    :return:
    """
    n, h, w = seq_array.shape
    for i in range(n):
        img = test_imgen.make_text_fast("{:06n}".format(startnum+i), seq_array[i, :, :], width=w, height=h, margins =(200,200,200,200))
        seq_array[i, :, :] = img
    return


@nb.jit(nb.void(nb.boolean[:,:,:]), parallel=True, nopython=True)
def random_sequence_generator(arr):
    """
    Fast random bit matrix generator order (3x over numpy.random.randint)

    :param arr: array to write to.
    """
    n, h, w = arr.shape
    for i in nb.prange(n):
        for j in range(h):
            for k in range(w):
                arr[i, j, k] = random.getrandbits(1)


def generate_whitenoise_sequence(seq_array_bool, seq_array, scale: int, debug=False, mask=None, **kwargs):
    """ Generates a sequence for upload to DMD.

    :param seq_array_bool: boolean ndarray to write the random bits, dimensions (N_pix, H_dmd/scale, W_dmd/scale)
    :param seq_array: uint8 ndarray for upload with dimensions (N_pix, H_dmd, W_dmd)
    :param scale: scale for discreet random pixels in DMD space. ie if scale=2, each random pixel will be
    projected as 2x2 pix on the dmd.
    :param debug: use numeric debug sequence generator to test synchronization.
    """
    if not debug:
        random_sequence_generator(seq_array_bool)
        zoomer(seq_array_bool, scale, seq_array)
    else:
        global _DEBUG_COUNTER  # a bit messy, but I don't want to spend to much time on the debug cleanliness.
        # _DEBUG_COUNTER += seq_array_bool.shape[0]
        number_sequence_generator(_DEBUG_COUNTER, seq_array)
        _DEBUG_COUNTER += seq_array_bool.shape[0]
    # print(seq_array.mean())
    seq_array[:] *= mask  # mask is 1 in areas we want to stimulate and 0 otherwise. This is faster than alternatives.


if __name__ == '__main__':
    pth = r"D:\tester.h5"
    mskfile = r"D:\patters\mouse_11102\mask_right_bulb.npy"
    main(1 * 10 ** 6, pth, generate_whitenoise_sequence, file_overwrite=True, seq_debug=False, picture_time=10 * 1000, mask_filepath=mskfile)
