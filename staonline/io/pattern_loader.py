"""
Classes for loading pattern stimulation image arrays from disk.
"""
from string import ascii_lowercase
from scipy import sparse
import numpy as np
from itertools import count
from abc import ABC, abstractmethod
import os
from glob import glob


class PatternLoader:
    """
    loads patterns from sparse matrix data format
    """
    def __init__(self, working_dir, file_prefix):

        self.current_frame = 0

        self._working_dir = working_dir
        self.file_prefix = file_prefix
        self._file_start = os.path.join(working_dir, file_prefix)
        mask_fn = self._file_start + '_mask.npy'
        self.mask = np.load(mask_fn)
        self.group_counter = AlphaCounter()
        self.group_current = self.group_counter.next()  # start at "aaa"
        self.group_next = self.group_counter.next()
        self.leaf_counter = 0

    def pathmaker(self, group, number):
        return '{}_{}:{:06n}.sparse.npz'.format(self._file_start, group, number)

    def get_next(self):
        """
        Returns a sparse array with the new frames that are available.
        :return:
        """
        matrices = self._read_files()
        if not matrices:
            return None
        stacked_mats = sparse.vstack(matrices)
        n, w = stacked_mats.shape
        end = self.current_frame + n
        pd = PatternData(stacked_mats, self.current_frame, end)
        self.current_frame = end
        return pd

    def _read_files(self):
        """
        Read all the files that are available for the same group that we're in,
        then try to read any new files that exist in the next group if there are any.

        This is a subroutine of get_next so that we can move through new groups recursively.

        :return: list of sparse matrices.
        """

        matrices = []
        path = self.pathmaker(self.group_current, self.leaf_counter)

        while os.path.exists(path):
            matrix = sparse.load_npz(path)
            matrices.append(matrix)
            self.leaf_counter += 1
            path = self.pathmaker(self.group_current, self.leaf_counter)

        if glob(self._file_start + '_{}*'.format(self.group_next)):
            self.leaf_counter = 0
            self.group_current = self.group_next
            self.group_next = self.group_counter.next()
            new_mats = self._read_files()
            matrices.extend(new_mats)

        return matrices


class PatternData:
    def __init__(self, frames:sparse.csr_matrix, n_start:int, end:int):
        self.frames = frames
        self.start = n_start
        self.end = end

    def n_frames(self):
        return self.end - self.start


class AlphaCounter:
    """
    Simple counter that counts in lowercase letters instead of numbers (ie aaa, aab, aac...).
    """

    def __init__(self, start_pos=0):
        self._count_num = start_pos

    def next(self):
        """
        returns the next alpha in the count.
        """
        l = len(ascii_lowercase)
        p1 = self._count_num % l
        p2 = self._count_num // l
        p3 = self._count_num // l ** 2
        self._count_num += 1
        return "{}{}{}".format(ascii_lowercase[p3], ascii_lowercase[p2], ascii_lowercase[p1])


if __name__ == '__main__':
    pth = '/Users/chris/Desktop/DmdLib/dmdlib/randpatterns/tests/tst'
    ptnLoader = PatternLoader(pth, 'testsparse')
    mats = ptnLoader.get_next()

