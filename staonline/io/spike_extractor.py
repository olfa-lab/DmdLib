import numpy as np
from scipy import signal
from concurrent import futures
import staonline.io.storage as storage


class SpikeExtractor:
    """
    Extracts spikes and frametimes from a datastore.
    """
    def __init__(self, data_source:storage.DatReader, spike_threshold=3.5, chs_neural=range(64), ch_frames=68, n_threads=6):
        """
        :param data_source: Data source object with a get_next() method
        :param spike_threshold:
        :param chs_neural: List of neural channels to process
        :param ch_frames: Channel containing frame times
        :param n_threads: number of threads to run processing in. (default 6)
        """

        self.storage = data_source
        self.executor = futures.ThreadPoolExecutor(n_threads)
        self.threshold = spike_threshold
        self.chs_neural = chs_neural          # Neural channels to process
        self.ch_frame_trig = ch_frames        # Frame channel

        self._last_frame_high = False
        self._read_samples = 0

    def get_next(self):
        """
        Gets data from data source and extracts spiketimes and frametimes relative to the start of the

        :return: tuples of spiketimes, and frametimes.
        """
        data = self.storage.get_next()
        if data is None:
            # No new spike and frame times, return empty arrays
            out1 = np.array([])
            out2 = np.array([])
            return out1, out2

        p_data = np.full((len(self.chs_neural), data.shape[1]), True, dtype=bool)
        my_futures = {self.executor.submit(self.process_channel, data[x, :], self.threshold): x for x in self.chs_neural}
        my_futures[self.executor.submit(self.get_frametimes, data[self.ch_frame_trig, :])] = 'FLAG'
        index = 0      # For indexing into p_data
        # Store processed channels in order of completion
        for future in futures.as_completed(my_futures):
            ch_ind = my_futures[future]
            if not ch_ind == 'FLAG':
                try:
                    bool_channel = future.result()
                except Exception as exc:
                    print('Row %r generated an exception: %s' % (ch_ind, exc))
                else:
                    p_data[index, :] = bool_channel
                    index += 1
            else:
                frametimes = future.result()
        mua_data = np.logical_or.reduce(p_data)
        spk_times = np.convolve(mua_data, np.array([1, -1]), mode='full')
        spk_times = np.where(spk_times == 1)[0]
        spk_times += self._read_samples
        frametimes += self._read_samples
        self._read_samples += data.shape[1]
        return spk_times, frametimes

    @staticmethod
    def process_channel(channel, threshold=3.5,  fs=30000):
        """

        :param channel:
        :param threshold:
        :param fs:
        :return:
        """
        nband = [x * 1 / (fs / 2) for x in [300, 9000]]
        b, a = signal.butter(5, nband, 'bandpass')
        channel = signal.filtfilt(b, a, channel)
        my_thresh = -channel.std()*threshold
        out = channel < my_thresh
        return out

    def get_frametimes(self,frame_channel):
        """
        :param frame_channel: numpy array holding frame onset/offset raw data
        :return: array of integers
        """

        # Extract frame onset times
        threshold = 15000
        bool_frame_channel = frame_channel > threshold
        frame_times = np.convolve(bool_frame_channel, np.array([1, -1]), mode='full')
        frame_times = np.where(frame_times == 1)[0]

        # Check if we ended high on last data pull and this data pull
        # starts high, we ignore first on-frame to prevent doublecounting
        if self._last_frame_high and frame_times[0] == 0:
            frame_times = frame_times[1:]

        # Check if we ended high on this data pull
        if bool_frame_channel[-1]:
            self._last_frame_high = True
        else:
            self._last_frame_high = False

        return frame_times

