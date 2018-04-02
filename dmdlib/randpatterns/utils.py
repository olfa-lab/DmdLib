import os
import concurrent.futures
from dmdlib.core.ALP import *
import tables as tb
import numpy as np
from tqdm import tqdm, trange
from ctypes import *
from dmdlib.randpatterns import ephys_comms
from string import ascii_lowercase
import warnings
import time
import uuid
import numba as nb
import argparse


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('savefile', help='path to save sequence data HDF5 (.h5) file')
    parser.add_argument('maskfile', help='path to mask file (.npy) file')
    parser.add_argument('--pic_time', type=int, default=10000, help='time to display each frame in us')
    parser.add_argument('--overwrite', action='store_true', help='overwrite datafile?')
    parser.add_argument('--nframes', type=int, default=750000, help='total number of frames to present before stopping')
    parser.add_argument('--scale', type=int, default=4, help='scale factor for pixels. NxN physical pixels are treated as a single logical pixel')
    parser.add_argument('--frames_per_run', type=int, default=60000, help='number of frames to present for each run')
    parser.add_argument('--no_phys', action='store_true', help="bypass connection to openephys for testing")
    return parser


def reshape(random_unshaped_array, mask_array, seq_array_bool):
    """ Reshapes a random bool array into the correct shape. Modifies seq_array_bool in place.

    :param random_unshaped_array:
    :param valid_array: boolean 2d array describing where the random values in random_unshaped_array should be placed.
    :param seq_array_bool: 3d array (nframes, h, w) with the shape of a (scaled) sequence to be uploaded.
    :return: none (in place modification of seq_array_bool)
    """

    n_frames, h, w = seq_array_bool.shape
    n_valid = mask_array.sum()

    random_unshaped_array.shape = n_frames, n_valid
    seq_array_bool.shape = n_frames, h * w
    seq_array_bool[:, mask_array.ravel()] = random_unshaped_array
    seq_array_bool.shape = n_frames, h, w
    random_unshaped_array.shape = -1


@nb.jit(parallel=True, nopython=True)
def zoomer(arr_in, scale, arr_out):
    """
    Fast nd array image rescaling for 3 dimensional image arrays expressed as numpy arrays.
    Writes directly to arr_out. ARR_OUT MUST be the correct size, as numba has weak boundary checking!!!!

    :param arr_in: boolean array
    :param scale: scale value. 1 pixel in arr in will be scale by scale pixels in output array.
    :param arr_out: array to write to.
    """
    a, b, c = arr_in.shape
    for i in nb.prange(a):
        for j in range(b):
            j_st = j * scale
            j_nd = (j + 1) * scale
            for k in range(c):
                k_st = k * scale
                k_nd = (k + 1) * scale
                if arr_in[i, j, k]:
                    arr_out[i, j_st:j_nd, k_st:k_nd] = 255
                else:
                    arr_out[i, j_st:j_nd, k_st:k_nd] = 0


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

