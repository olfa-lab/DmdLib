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
from .saving import HfiveSaver

from .utils import zoomer, find_unmasked_px

class Presenter:
    def __init__(self, dmd: AlpDmd, pattern_generator, saver: HfiveSaver, total_presentations=-1,
                 nseqs=3, pix_per_seq=250, nbits=1, picture_time=10000, image_scale=4,
                 seq_debug=False):
        """
        :param dmd: AlpDmd object
        :param save_path: path to savefile. This file should exist!!
        :param save_groupname: hdf5 groupname for saving the patterns.
        :param pattern_generator: function for generating images to upload.
        :param total_presentations: total images to present (optional, can be handled by seq_generator)
        :param nseqs: sequences to upload.
        :param pix_per_seq: pix per sequence.
        :param nbits: bitdepth of uploaded file
        :param picture_time: time in microseconds to display each frame.
        :param image_scale: defines the logical pixel size for the random patterns relative to the physical DMD pixels.
        :param seq_debug:
        :param mask:
        :param kwargs:
        """

        # todo correct the number of sequences to upload...
        self.dmd = dmd
        dmd.proj_mode('master')
        self.saver = saver
        self.pattern_generator = pattern_generator
        self._last_upload_num = 0
        self.image_scale = image_scale
        self._sequence_freshness = {}
        self.pix_per_seq = pix_per_seq
        self.sequences = self._setup_sequences(nseqs, nbits, pix_per_seq, picture_time)
        self.seq_array_bool = np.zeros((pix_per_seq, self.dmd.h // self.image_scale, self.dmd.w // self.image_scale),
                                       dtype=bool)
        self.sequence_counter = 0
        self.total_presentations = total_presentations
        self.dmd_proj_status = None
        self.frames_presented = 0
        self.seq_debug = seq_debug


    def run(self):
        """
        starts a run.
        :return:
        """
        self._upload_initial_sequences()
        for s in sorted(self.sequences.values()):  # start in order.
            s.start_projection()

        with tqdm(total=self.total_presentations, desc='Presenting images', unit='img') as pbar:
            while self.dmd.projecting == ALP_PROJ_ACTIVE:
                # update progress bar:
                progress_struct = self._update_projector_progress()
                frames_uploaded_total = self.sequence_counter * self.pix_per_seq
                frames_in_buffer = (progress_struct.nWaitingSequences + 1) * self.pix_per_seq
                _frames_presented = frames_uploaded_total - frames_in_buffer
                pbar.update(_frames_presented - self.frames_presented)
                self.frames_presented = _frames_presented

                # upload new frame sequences:
                if frames_uploaded_total < self.total_presentations:
                    refresh = self._gen_refresh(progress_struct.SequenceId)
                    for seq_id in refresh:
                        seq = self.sequences[seq_id]  #type: AlpFrameSequence
                        self.update_sequence(seq)
                        seq.start_projection()
                        self._update_projector_progress()  # call this often to make sure we don't miss a sequence.
                time.sleep(.1)  # sleep for 100 ms
            pbar.update(self.pix_per_seq)

    def _update_projector_progress(self):
        """
        :return:
        """

        unfresh = 0
        progress = self.dmd.get_projecting_progress()
        curr_seq = progress.SequenceId
        try:
            self._sequence_freshness[curr_seq] = False
            unfresh += 1
        except KeyError as e:
            # the only time we should get a keyerror is if we've stopped projecting and the dmd returns rubbish.
            # so check if we're projecting and if we are, raise the keyerror.
            if self.dmd.projecting == ALP_PROJ_ACTIVE:
                raise e
        return progress

    def _gen_refresh(self, current_sequence_id):
        """

        :param current_sequence_id: c_long representing the currently displayed sequence.
        :return: list of sequence-ids for which updates are required.
        """
        refresh = []
        for k, v in self._sequence_freshness.items():
            if not v and k != current_sequence_id:
                refresh.append(k)
        return refresh

    def _upload_initial_sequences(self):
        for s in tqdm(self.sequences.values(), desc="Uploading initial sequences", unit='seq'):  #type: AlpFrameSequence
            self.update_sequence(s)

    def update_sequence(self, sequence: AlpFrameSequence):
        self.pattern_generator.make_patterns(self.seq_array_bool, sequence.array, self.seq_debug)
        sid = int(sequence)
        seq_meta_dict = {
            'sync_pulse_dur_us': sequence.syncpulsewidth,
            'seq_id': sid,
            'image_scale': self.image_scale,
            'picture_time_us': sequence.picturetime
        }
        self.saver.store_sequence_array(self.seq_array_bool.astype(bool), seq_meta_dict)  # watch out when
        sequence.upload_array()
        self._sequence_freshness[sid] = True
        self.sequence_counter += 1

    def _setup_sequences(self, nseqs, nbits, pix_per_seq, picture_time):
        seqs = {}
        seq_pulse_lens = self._make_seq_pulse_lens(nseqs, picture_time - 500)
        for i in range(nseqs):
            seq = self.dmd.seq_alloc(nbits, pix_per_seq)
            seqid = seq.seq_id.value
            seqs[seqid] = seq
            pw = seq_pulse_lens[i]
            seq.set_timing(picturetime=picture_time, syncpulsewidth=pw)
            self._sequence_freshness[seqid] = False
            if nbits == 1:
                self.dmd._AlpSeqControl(seq.seq_id, ALP_BIN_MODE, ALP_BIN_UNINTERRUPTED)
        return seqs

    @staticmethod
    def _make_seq_pulse_lens(n_vals, max_val, min_val=100, min_diff=100):
        """
        Makes a "random" list of integers between min_time and max_time and ensures that each value spaced at least min_diff
        away from all the other values.

        :param n_vals: number of values to return
        :param max_val: maximum value that any number in the list can have
        :param min_val: minimum value that any number in the list can have
        :param min_diff: all values must be at least this far apart from each other.
        :return: list of pulse lengths.
        """

        def distance_checker(proposed, existing, min_dist=100):
            for v in existing:
                if np.abs(v - proposed) < min_dist:
                    return False
            return True

        pulse_lens = []
        for i in range(n_vals):
            good = False
            while not good:
                val = np.random.randint(min_val, max_val)
                good = distance_checker(val, pulse_lens, min_diff)
            pulse_lens.append(val)
        return pulse_lens

    def shutdown(self):
        if hasattr(self, 'sequences'):
            self.sequences.clear()

    def __del__(self):
        self.shutdown()
