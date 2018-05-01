import numpy as np
from scipy import sparse
import numba as nb
from collections import deque

from staonline.io import pattern_loader, spike_extractor, storage

class StaMaker:
    def __init__(self,
                 spike_source:spike_extractor.SpikeExtractor,
                 pattern_source:pattern_loader.PatternLoader,
                 spike_window_start=300, spike_window_end=900):
        """

        :param spike_source:
        :param pattern_source:
        :param spike_window_start:
        :param spike_window_end:
        """
        self._image_count = 0
        self.pattern_source = pattern_source
        self.spike_source = spike_source
        self.all_spikes = np.array([])
        self.all_frametimes = np.array([])
        self._spike_window_start = spike_window_start
        self._spike_window_end = spike_window_end

        self.pattern_q = deque()
        self.frames_processed = 0
        self.sta = None

    def update(self):
        new_spikes, new_frametimes = self.spike_source.get_next() # type: np.array
        self.all_spikes = np.concatenate((self.all_spikes, new_spikes))
        self.all_frametimes = np.concatenate((self.all_frametimes, new_frametimes))
        new_frames = self.pattern_source.get_next()  # type: sparse.csr_matrix
        if new_frames:
            self.pattern_q.append(new_frames)

        n_frametimes = len(self.all_frametimes)
        n_unprocessed_frametimes = n_frametimes - self.frames_processed

        while self.pattern_q and n_unprocessed_frametimes >= self.pattern_q[0].n_frames():
            next_frameblock = self.pattern_q.popleft()  # type: pattern_loader.PatternData
            sta = self.update_sta(
                self.all_spikes,
                self.all_frametimes[self.frames_processed:self.frames_processed + next_frameblock.n_frames()],
                next_frameblock
            )

            if self.sta is None:
                self.sta = sta
            else:
                self.sta += sta

            self.frames_processed += next_frameblock.n_frames()
            n_unprocessed_frametimes -= next_frameblock.n_frames()

    def calc_stc(self, spiketimes, frametimes, frame_data:pattern_loader.PatternData):
        """
        First we're going to calculate the number of spikes that fall in the bintimes after our frames
        were presented. This is optimized and a bit hard to read, but we're using binary search to quickly
        determine how many spikes occur within bins.

        Then take the dot product of our counts per frame with our frames x pixels matrix. This returns
        an array of length pixels.

        :param spiketimes: array of spiketimes.
        :param frametimes: array of frametimes
        :param frame_data: PatternData object
        :return:
        """


        # find how many spikes fall within the bins following our frame presentations:
        start_stop_times = np.zeros(len(frametimes.frames, 2), 'uint32')

        start_stop_times[:, 0] = frametimes + self._spike_window_start
        start_stop_times[:, 1] = frametimes + self._spike_window_end

        searches = np.searchsorted(spiketimes, start_stop_times.ravel())
        searches.shape = start_stop_times.shape
        counts = np.diff(searches)

        stc = frame_data.frames.T.dot(counts.ravel())

        return stc


def main(filename, patterndir, pattern_prefix):

    store = storage.DatReader(filename)  # neural channels....
    se = spike_extractor.SpikeExtractor(store, spike_threshold=3)
    patterloader = pattern_loader.PatternLoader(patterndir, pattern_prefix)

    sta = StaMaker(se, patterloader)


