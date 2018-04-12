import numpy as np
from os.path import getsize


class Storage:
    def __init__(self, filename, nch=75, fs=30000, nsec=10):
        self.data = np.array([])
        self.filename = filename  # File to read from
        self.pos = 0              # Position in file
        self.nch = nch            # Number of recording channels
        self.fs = fs              # Sampling frequency
        self.nsec = nsec          # Max amount of data to load at a time (in seconds)

    def get_next(self):
        with open(self.filename, 'rb') as fr:
            fr.seek(self.pos)  # Move to current position
            self.pos = getsize(self.filename)  # Update position in file...
            # Load a maximum of self.nsec seconds of data
            if self.pos - fr.tell() < 2 * self.nsec * self.fs * self.nch:
                self.data = np.fromfile(fr, dtype='int16')
            else:
                self.data = np.fromfile(fr, count=self.nsec * self.fs * self.nch, dtype='int16')
            self.data = np.reshape(self.data, [self.nch, int(self.data.size / self.nch)], order='F')
        fr.close()
        return self.data
