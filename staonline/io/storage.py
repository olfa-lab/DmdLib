import numpy as np
import os


class DatReader:
    """
    Reads data incrementally from flat binary file (dat).
    """
    def __init__(self, filename, nch=75, fs=30000, max_read_secs=10):
        """
        :param filename:
        :param nch: TOTAL number of channels in the array
        :param fs: default 30000 khz
        :param max_read_secs: maximum amount of data to return in seconds.
        """

        self.filename = filename        # File to read from
        self.pos = 0                    # Position in file
        self.nch = nch                  # Number of recording channels
        self.fs = fs                    # Sampling frequency
        self.max_secs = max_read_secs   # Max amount of data to load at a time (in seconds)
        self.min_secs = 1               # Min amount of data to read (in seconds)

        self._bytes_per_sample = 2 # datatype is int16
        self._max_read_samples = self.max_secs * fs * nch
        self._max_read_bytes = self._max_read_samples * 2
        self._bytes_per_row = self._bytes_per_sample * self.nch
        self._min_read_samples = self.min_secs * fs * nch
        self._min_read_bytes = self._min_read_samples * self._bytes_per_sample

    def get_next(self):
        """
        returns the next data array from the file.
        :return:
        """

        # calculate how much new data we have in bytes and verify that we have at least the minimum amount of
        # data, otherwise return None.
        current_file_len = os.path.getsize(self.filename)  # Update position in file...
        current_file_len_full_rows = current_file_len - current_file_len % self._bytes_per_row
        # ^ modulo makes sure we're reading a whole row so we can reshape.
        new_bytes = current_file_len_full_rows - self.pos
        if new_bytes < self._min_read_bytes:
            return None

        # We're going to read the next 10 seconds or whatever data is available in the file:
        read_to_pos = min(
            (current_file_len_full_rows,
             self._max_read_bytes + self.pos)
        )

        assert not read_to_pos % self._bytes_per_sample
        # Number of values to read into numpy array
        read_count_values = (read_to_pos - self.pos) // self._bytes_per_sample

        with open(self.filename, 'rb') as fr:
            fr.seek(self.pos)
            data = np.fromfile(fr, count=read_count_values, dtype='int16')

        data = np.reshape(data, [self.nch, data.size // self.nch], order='F')

        self.pos = read_to_pos  # this is where we'll seek in the next read.
        return data
