import numpy as np
from scipy import signal
from concurrent import futures

class SpikeExtractor:

    def __init__(self, storage):
        self.storage = storage
        self.executor = futures.ThreadPoolExecutor()

    def get_next(self):
        data = self.storage.get_next()
        p_data = np.full(data.shape, True, dtype=bool)
        my_futures = {self.executor.submit(process_channel, data[x, :]): x for x in range(self.storage.nch)}
        # Store processed channels in order of completion
        for future in futures.as_completed(my_futures):
            ch = my_futures[future]
            try:
                tmp = future.result()
            except Exception as exc:
                print('Row %r generated an exception: %s' % (ch, exc))
            else:
                p_data[ch, :] = tmp
        mua_data = np.logical_or.reduce(p_data)
        spk_times = np.convolve(mua_data, np.array([1, -1]), mode='full')
        spk_times = np.where(spk_times == 1)[0]
        return spk_times

    @staticmethod
    def process_channel(channel, fs=30000):
        nband = [x * 1 / (fs / 2) for x in [300, 800]]
        b, a = signal.butter(4, nband, btype='band')
        channel = signal.filtfilt(b, a, channel)
        mu = np.mean(channel)
        sd = np.std(channel)
        out = channel > mu + 3 * sd
        return out