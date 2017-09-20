import os
import concurrent.futures
from dmdlib.ALP import *
import tables as tb
import numpy as np
import logging
import argparse
from tqdm import tqdm, trange
import test_imgen
from ctypes import *
import numba as nb
import random
import ephys_comms
from string import ascii_lowercase
import warnings
import time
import uuid

warnings.filterwarnings('ignore', category=tb.NaturalNameWarning)

count = 1
dmd = DMD()
dmd.seq_queue_mode()
dmd.proj_mode('master')
rv = c_long()

saver = concurrent.futures.ThreadPoolExecutor(1)

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
                if arr_in[i, j, k]:
                    k_st = k * scale
                    k_nd = (k + 1) * scale
                    arr_out[i, j_st:j_nd, k_st:k_nd] = 255


def setup_record(filename, uuid=''):
    """
    Creates seq recording file. Add to record using save_sequence method below.

    :param filename: name of file to create.
    """
    with tb.open_file(filename, 'w', title="Rand_pat_file_v1:{}".format(uuid)) as f:
        f.create_group('/', 'patterns', tb.Filters(5))
    return


def save_sequence(filename, save_groupname, leaf_id, data, metadata={}):
    """
    Adds a seqence matrix to the file created with setup_record. The call to create_carray does not hold the GIL, so
    this can be used effectively with multithreading.

    Since we are usually presenting scaled images on the DMD, this method has facilities for adding a display scale
    integer to the attribute of the sequence array. This can be used later to reconstruct the entire image using zoomer
    or equivalent methods instead of saving the (huge) display array.

    :param filename: path to savefile created with setup_record.
    :param leaf_id: name for new sequence leaf
    :param data: numpy array to save.
    :param disp_scale: scale at which the object is displayed.
    :return:
    """
    with tb.open_file(filename, 'r+') as f:
        arr = f.create_carray('/patterns/{}'.format(save_groupname), '{:06n}'.format(leaf_id),
                              obj=data, filters=tb.Filters(4, shuffle=False), createparents=True)  # shuffle doesn't help w/ random data.
        for k, v in metadata.items():
            arr.set_attr(k, v)
    return


def generate_upload(seq_array_bool, seq_array, scale: int, debug=False, mask=None):
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


def gen_refresh(freshness, current):
    refresh = []  # want to refresh lowest numbers first.
    for k, v in freshness.items():
        if not v and k != current:
            refresh.append(k)
    return [c_long(x) for x in refresh]


def update_status(status_ptr, freshness_dict):
    dmd.AlpProjInquireEx(ALP_PROJ_PROGRESS, byref(status_ptr))
    curr_seq = status_ptr.SequenceId
    unfresh = 0
    try:  # we can have a situation where we get a fake sequence id when the DMD stops projecting
        freshness_dict[curr_seq] = False
        unfresh += 1
    except KeyError as e:
        # the only time we should get a keyerror is if we've stopped projecting and the dmd returns rubbish.
        # so check if we're projecting and if we are, raise the keyerror.
        proj = c_long()
        dmd.AlpProjInquire(ALP_PROJ_STATE, byref(proj))
        if proj.value == ALP_PROJ_ACTIVE:
            raise e
    return unfresh


class AlphaCounter():
    def __init__(self, start_pos=0):
        self._counter = start_pos

    def next(self):
        """
        returns the next alpha in the count.
        """
        l = len(ascii_lowercase)
        p1 = self._counter % l
        p2 = self._counter // l
        p3 = self._counter // l ** 2
        self._counter += 1
        return "{}{}{}".format(ascii_lowercase[p3], ascii_lowercase[p2], ascii_lowercase[p1])


def presenter(
        total_presentations: int, save_path: str, save_groupname: str, nseqs=3, pix_per_seq=250, nbits=1,
        picture_time=1000 * 10, image_scale=4, seq_debug=False, mask=None
):
    """

    :param total_presentations: total images to present
    :param save_path: path to savefile. This file should exist!!
    :param nseqs: sequences to upload.
    :param pix_per_seq: pix per sequence.
    :param nbits: bitdepth of uploaded file
    :param picture_time: time in microseconds to display each frame.
    :param image_scale: defines the logical pixel size for the random patterns relative to the physical DMD pixels.
    ie '4' will mean that the random pattern will be made up of H_dmd/4 by W_dmd/4 logical pixels.
    """
    if dmd.w % image_scale or dmd.w % image_scale:
        errst = "image_scale parameter must evenly divide into DMD's physical width and height ({}x{})".format(dmd.w, dmd.h)
        raise ValueError(errst)
    # fut = saver.submit(setup_record, save_path)
    if total_presentations < nseqs * pix_per_seq:
        nseqs = np.ceil(total_presentations / pix_per_seq)
    # INITIALIZE DMD
    last_uploaded_image_number = 0
    sequence_ids = [c_long() for x in range(nseqs)]  # can't use [c_long()]*nseqs because all are the same memory.
    pix_per_seq_c = c_long(pix_per_seq)  # cache this for use later
    nbits_c = c_long(nbits)
    offset_c = c_long(0)
    picture_time_c = c_long(picture_time)
    seq_array_bool = np.zeros((pix_per_seq, dmd.h // image_scale, dmd.w // image_scale), dtype=bool)
    seq_array = np.zeros((pix_per_seq, dmd.h, dmd.w), dtype='uint8')
    seq_array_ptr = seq_array.ctypes.data_as(POINTER(c_char))
    sequence_freshness = {}  # dict keeping track of which sequences in ALP memory have been displayed or are "fresh"
    sequence_pulse_lengths = {}  # dict that tracks the sync pulse width used for synchronization later.
    dmd_proj_status = AlpProjProgress()  # data structure updated by AlpProjInquireEx
    projecting = c_long()
    frames_presented = 0  # count of frames presented for status viewer.
    seq_counter = 0  # running count of the number of sequences that have been uploaded - this defines the name of the save leaf.
    for i in range(nseqs):
        dmd.AlpSeqAlloc(nbits_c, pix_per_seq_c, byref(sequence_ids[i]))
        seq_id = sequence_ids[i]
        sequence_freshness[seq_id.value] = False
        sync_pulse_len = np.random.randint(500, picture_time-500)
        sequence_pulse_lengths[seq_id.value] = sync_pulse_len
        dmd.AlpSeqTiming(seq_id, picturetime=picture_time_c, syncpulsewidth=c_long(sync_pulse_len))
        if nbits == 1:
            dmd.AlpSeqControl(seq_id, ALP_BIN_MODE, ALP_BIN_UNINTERRUPTED)
    for i in trange(nseqs, desc='Uploading initial sequences', unit='seq'):
        seq_id = sequence_ids[i]
        generate_upload(seq_array_bool, seq_array, image_scale, seq_debug, mask)
        seq_meta_dict = {
            'sync_pulse_dur_us': sequence_pulse_lengths[seq_id.value],
            'seq_id': seq_id.value,
            'image_scale': image_scale,
            'picture_time_us': picture_time
        }
        saver.submit(save_sequence, save_path, save_groupname, seq_counter, seq_array_bool.astype(bool), seq_meta_dict)  # .astype is copying, so we're thread safe here.
        seq_counter += 1
        dmd.AlpSeqPut(seq_id, offset_c, pix_per_seq_c, seq_array_ptr)
        last_uploaded_image_number += pix_per_seq
        sequence_freshness[seq_id.value] = True

    # todo: check that sequence length << check interval!!
    with tqdm(total=total_presentations, desc="Presenting images", unit='img') as pbar:
        for seq_id in sequence_ids:
            dmd.AlpProjStart(seq_id)
        dmd.AlpProjInquire(ALP_PROJ_STATE, byref(projecting))
        while projecting.value == ALP_PROJ_ACTIVE:
            update_status(dmd_proj_status, sequence_freshness)
            _frames_presented = last_uploaded_image_number - ((dmd_proj_status.nWaitingSequences + 1) * pix_per_seq)
            pbar.update(_frames_presented - frames_presented)
            frames_presented = _frames_presented
            if last_uploaded_image_number < total_presentations:
                refresh = gen_refresh(sequence_freshness, dmd_proj_status.SequenceId)
                for seq_id in refresh:
                    generate_upload(seq_array_bool, seq_array, image_scale, seq_debug, mask)
                    seq_meta_dict = {
                        'sync_pulse_dur_us': sequence_pulse_lengths[seq_id.value],
                        'seq_id': seq_id.value,
                        'image_scale': image_scale,
                        'picture_time_us': picture_time
                    }
                    saver.submit(save_sequence, save_path, save_groupname, seq_counter, seq_array_bool.astype(bool), seq_meta_dict)
                    seq_counter += 1
                    dmd.AlpSeqPut(seq_id, offset_c, pix_per_seq_c, seq_array_ptr)
                    sequence_freshness[seq_id.value] = True
                    dmd.AlpProjStart(seq_id)
                    last_uploaded_image_number += pix_per_seq
                    update_status(dmd_proj_status, sequence_freshness)  # just so that we don't miss any invalidations while we're refreshing.
            time.sleep(.25)
            dmd.AlpProjInquire(ALP_PROJ_STATE, byref(projecting))
        pbar.update(pix_per_seq)  # todo: this is a hack...


def main(total_presentations, save_filepath, mask_filepath=None, picture_time=1000 * 10, image_scale=4, file_overwrite=False,
         seq_debug=False):

    if mask_filepath:
        mask = np.load(mask_filepath)  # the mask is true in the area we want to illuminate.
    else:
        mask = None
    fullpath = os.path.abspath(save_filepath)
    if not file_overwrite and os.path.exists(save_filepath):
        errst = "{} already exists.".format(fullpath)
        raise FileExistsError(errst)
    patternfile_uuid = uuid.uuid4()
    ephys_comms.send_message('Pattern file saved at: {}.'.format(fullpath))
    ephys_comms.send_message('Pattern file uuid: {}.'.format(patternfile_uuid))
    setup_record(save_filepath, uuid=patternfile_uuid)
    presentations_per = 60000  # 1 minutes of recording @ 100 Hz framerate.
    n_runs = int(np.ceil(total_presentations / presentations_per))
    presentation_run_counter = AlphaCounter()
    for i in range(n_runs):
        run_id = presentation_run_counter.next()
        print("Starting presentation run {} of {} ({}).".format(i+1, n_runs, run_id))
        ephys_comms.send_message('Starting presentation {}'.format(run_id))
        presenter(presentations_per, save_filepath, run_id, picture_time=picture_time,
                  image_scale=image_scale, seq_debug=seq_debug, mask=mask)
    print('waiting for saver to shutdown...')
    saver.shutdown()


if __name__ == '__main__':
    pth = r"D:\patters\mouse_11102\pats_run3.h5"
    mskfile = r"D:\patters\mouse_11102\mask_right_bulb.npy"
    main(1*10**6, pth, file_overwrite=False, seq_debug=False, picture_time=10*1000, mask_filepath=mskfile)
