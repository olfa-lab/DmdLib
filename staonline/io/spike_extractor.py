import numpy as np
from scipy import signal
from concurrent import futures
import staonline.io.storage as storage


class SpikeExtractor:
    """
    Extracts spikes and frametimes from a datastore.
    """
    def __init__(self, data_source:storage.DatReader, spike_threshold=3., chs_neural=range(64), ch_frames=73, n_threads=6):
        """
        :param data_source: Data source object with a get_next() method
        :param spike_threshold:
        :param chs_neural:
        :param ch_frames:
        :param n_threads: number of threads to run processing in. (default 6)
        """

        self.storage = data_source
        self.executor = futures.ThreadPoolExecutor(n_threads)
        self.threshold = spike_threshold

        # todo: generate neural channels here - not all channels should be spike extracted.
        self.chs_neural = chs_neural
        self.ch_frame_trig = ch_frames

    def get_next(self):
        """
        Gets data from data source and extracts spiketimes and frametimes relative to the start of the

        :return: tuples of spiketimes, and frametimes.
        """
        data = self.storage.get_next()
        if data is None:
            return None

        p_data = np.full(data.shape, True, dtype=bool)
        my_futures = {self.executor.submit(self.process_channel, data[x, :] ): x for x in self.chs_neural}
        # todo: my_futures[self.executor.submit(self.get_frametimes)] = 'FLAG'
        # Store processed channels in order of completion
        for future in futures.as_completed(my_futures):
            ch = my_futures[future]
            if not ch == 'FLAG':

                try:
                    tmp = future.result()
                except Exception as exc:
                    print('Row %r generated an exception: %s' % (ch, exc))
                else:
                    p_data[ch, :] = tmp
            else:
                frametimes = future.result()
        mua_data = np.logical_or.reduce(p_data)
        spk_times = np.convolve(mua_data, np.array([1, -1]), mode='full')
        spk_times = np.where(spk_times == 1)[0]
        return spk_times, frametimes

    @staticmethod
    def process_channel(channel, threshold=3.,  fs=30000):
        """

        :param channel:
        :param threshold:
        :param fs:
        :return:
        """
        nband = [x * 1 / (fs / 2) for x in [300, 800]]
        b, a = signal.butter(4, nband, btype='band')
        channel = signal.filtfilt(b, a, channel)
        mu = np.mean(channel)
        sd = np.std(channel)
        out = channel > mu + 3 * sd
        return out

    def get_frametimes(self):
        """

        :return: array of integers
        """

        #TODO

        # be careful if we end high on last data pull, so that we don't double-count
        # a frametrigger!!!
        pass

