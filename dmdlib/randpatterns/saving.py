"""
This contains apparatuses for saving patterns to the
"""
from concurrent import futures
import tables as tb
import uuid
from scipy import sparse
import numpy as np
from string import ascii_lowercase
import os
import warnings

warnings.filterwarnings('ignore', category=tb.NaturalNameWarning)


class Saver:
    """
    Base class for saving data in another thread
    """

    def __init__(self, nthreads=1):
        self._futures = []
        self._executor = futures.ThreadPoolExecutor(nthreads)  # IO bound so we'll use threads here.
        # self._store = self._setup_store()

    def _setup_saver(self, *args, **kwargs):
        pass

    def _check_futures(self, wait=False):
        """
        Checks if any futures are completed. If no futures are completed, return immediately. If any are completed with exceptions, raise
        the exceptions in the main thread.
        """

        if wait:
            timeout = None
        else:
            timeout = 0

        try:
            completed = futures.as_completed(self._futures, timeout)
            for fut in completed:  # type: futures.Future
                self._futures.remove(fut)
                if fut.exception():
                    raise fut.exception()

        except futures.TimeoutError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        When used in context, this ensures that submitted jobs will finish prior to python exiting to prevent
        data loss.
        """
        print("Waiting for save processes to join...", end='')
        self._executor.shutdown()
        print('complete.')


class HfiveSaver(Saver):
    """
    Saver object for pattern stimuation patterns.
    """

    def __init__(self, save_path, overwrite=False, ):
        """
        :param save_path: Path to where you want to save.
        :param overwrite:  default False. Set true to allow overwrite of existing files. Be careful.
        """

        super(HfiveSaver, self).__init__(nthreads=1)  # this MUST be 1 here, because writes to h5 are not threadsafe.
        self.path = save_path
        self.uuid = str(uuid.uuid4())
        self._patterngroupid = 'patterns'
        self._store = self._setup_store(save_path, self.uuid, overwrite)
        self._group_id_counter = AlphaCounter()
        self.current_group_id = ''
        self.current_leaf_id = 0
        self.iter_pattern_group()  # iterate to the first pattern group.

    def store_sequence_array(self, seq_array, attributes=None):
        """
        Adds a sequence to the h5 file into the current group. Relies on the state of the store to save. This
        wraps the _store_sequence static method, which can be used in another thread.

        WATCH OUT FOR THREAD SAFETY HERE. If you modify the array before it is written to disk, everything
        will break!!

        :param seq_array: numpy array to be saved
        :param attributes: metadata to be saved with the array.
        """

        self._check_futures()

        if attributes is None:
            attributes = {}
        groupname = '/{}/{}'.format(self._patterngroupid, self.current_group_id)
        leafname = '{:06n}'.format(self.current_leaf_id)

        a = self._executor.submit(self._store_sequence, self.path, groupname, leafname, seq_array, attributes)
        self._futures.append(a)
        self.current_leaf_id += 1

    @staticmethod
    def _store_sequence(filename, save_groupname, leafname, data, metadata):
        """
        static method for use in separate thread. This allows saving in another process, but it does not
        allow access to class state. As implemented, this is wrapped by store_sequence_array

        :return:
        """

        with tb.open_file(filename, 'r+') as f:
            arr = f.create_carray(save_groupname, leafname, obj=data, filters=tb.Filters(4, shuffle=False),
                                  createparents=True)
            # shuffle doesn't help w/ random data.
            for k, v in metadata.items():
                arr.set_attr(k, v)

    def store_mask_array(self, mask_array: np.ndarray):
        """
        Saves pixel array representing the masked pixels in the recording.
        :param mask_array: boolean numpy ndarray
        """
        self._check_futures(wait=True)  # wait for submitted jobs to complete before saving.
        with tb.open_file(self.path, 'r+') as f:
            f.create_array('/', 'pixel_mask', obj=mask_array)

    def store_affine_matrix(self, matrix: np.ndarray):
        """
        Adds affine transform matrix to the recording file.
        :param matrix: affine transform matrix
        """
        self._check_futures(wait=True)  # wait for submitted saves to complete before saving.
        with tb.open_file(self.path, 'r+') as f:
            f.create_array('/', 'affine', obj=matrix)

    def iter_pattern_group(self):
        """
        iterates the pattern group name to next
        :return:
        """
        self.current_group_id = self._group_id_counter.next()
        self.current_leaf_id = 0
        return self.current_group_id

    def _setup_store(self, path, uuid_str, overwrite=False):
        """

        :param path:
        :return:
        """

        if not overwrite and os.path.exists(path):
            raise FileExistsError('File already exists and overwrite is False.')
        elif overwrite and os.path.exists(path):
            print('Overwriting file at {}'.format(path))
        with tb.open_file(path, 'w', title="Rand_pat_file_v1:{}".format(uuid_str)) as f:
            f.create_group('/', self._patterngroupid, tb.Filters(5))


class SparseSaver(Saver):
    pass


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
