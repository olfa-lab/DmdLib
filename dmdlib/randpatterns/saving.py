"""
This contains apparatuses for saving patterns to disk.
"""
from concurrent import futures
import tables as tb
import uuid
from scipy import sparse
import numpy as np
from string import ascii_lowercase
import os
import warnings
from abc import abstractmethod, ABC
from glob import glob
import json
import csv

warnings.filterwarnings('ignore', category=tb.NaturalNameWarning)


class Saver(ABC):
    """
    Base class for saving data in another thread
    """

    def __init__(self, nthreads=1):
        self.uuid = str(uuid.uuid4())
        self._futures = []
        self._executor = futures.ThreadPoolExecutor(nthreads)  # IO bound so we'll use threads here.
        self._group_id_counter = AlphaCounter()
        self.current_leaf_id = 0
        self.iter_pattern_group()  # iterate to the first pattern group.

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

    @abstractmethod
    def store_mask_array(self, array: np.ndarray):
        pass

    @abstractmethod
    def store_sequence_array(self, array: np.ndarray):
        pass

    @abstractmethod
    def store_affine_matrix(self, matrix: np.ndarray):
        pass

    def iter_pattern_group(self) -> str:
        """
        iterates the pattern group name to next
        :return: the next group id string.
        """
        next_group = self._group_id_counter.next()
        self.current_group_id = next_group
        self.current_leaf_id = 0
        return next_group

    def flush(self):
        """ Wait for all futures to return (and all files to be written). """
        self._check_futures(True)


class HfiveSaver(Saver):
    """
    Saver object for pattern stimuation patterns.
    """

    def __init__(self, save_path, overwrite=False, attributes=None):
        """
        :param save_path: Path to where you want to save.
        :param overwrite:  default False. Set true to allow overwrite of existing files. Be careful.
        :param attributes: optional attributes dictionary to save as attributes of the root file.
        """
        super(HfiveSaver, self).__init__(nthreads=1)  # this MUST be 1 here, because writes to h5 are not threadsafe.
        self.path = save_path
        self._patterngroupid = 'patterns'
        self._setup_store(save_path, self.uuid, overwrite, attributes)

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

    def _setup_store(self, path, uuid_str, overwrite=False, attributes=None):
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
            if attributes and type(attributes) == dict:
                for k, v in attributes.items():
                    f.set_node_attr('/', k, v)


class SparseSaver(Saver):
    """
    Saver for sparse matrices.
    """

    _description = """ This is frame data saved as sparse matrices in the CSR format using the Scipy 
    sparse package. Frame metadata is saved within a csv file, which has the suffix and extension 
    '_framedata.csv'.
    """

    def __init__(self, working_dir, file_prefix, overwrite=False, attributes=None):
        """

        :param working_dir:
        :param file_prefix:
        :param overwrite:
        :param attributes:
        """
        super(SparseSaver, self).__init__()

        self.prefix = file_prefix
        self.savedir = working_dir
        assert os.path.exists(working_dir)

        self._path_start = os.path.join(working_dir, file_prefix)
        if not overwrite:
            self._check_existing(self._path_start)
        self._file_count = 0
        self.store_path = self._path_start + '.json'
        self._setup_store(self.store_path, self.uuid, attributes)
        self.framedata_path = self._path_start + '_framedata.csv'
        self._framedata_file = open(self.framedata_path, 'w')
        self._framedata_csv = None
        self._mask = None
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._framedata_file is not None:
            self._framedata_file.close()
        super(SparseSaver, self).__exit__(exc_type, exc_val, exc_tb)

    def _check_existing(self, path):
        """ Checks if files with the path+prefix combination exist and raises exeception if so...  """
        pattern = path + '*.sparse.npz'
        if glob(pattern):
            raise FileExistsError('Files exist with the pattern: {}'.format(pattern))

    def store_sequence_array(self, seq_array:np.ndarray, attributes=None):
        """
        :param seq_array: Sequence array to save. If this is a 3d array, it will be saved as a 2d sparse matrix.
        :param attributes: Dictionary
        :return:
        """

        if seq_array.ndim == 3 and self._mask is None:
            if attributes is None:
                attributes = {}
            npix, h, w = seq_array.shape
            attributes['n'], attributes['h'], attributes['w'] = npix, h, w
            seq_array.shape = npix, w * h

        elif seq_array.ndim == 3 and self._mask is not None:
            # only save the active pixels that are true in the mask.
            seq_array = seq_array[:, self._mask]  # shape = n_frames, n_pix that are 1 in the mask.

        if attributes is not None:
            if self._framedata_csv is None:
                self._setup_framedata(list(attributes.keys()))
            self._framedata_csv.writerow(attributes)

        savepath = "{}_{}-{:06d}.sparse.npz".format(self._path_start,
                                                    self.current_group_id,
                                                    self.current_leaf_id)
        self._store_sequence(savepath, seq_array)
        self.current_leaf_id += 1
        return

    @staticmethod
    def _store_sequence(npz_savepath: str, data: np.ndarray):
        sprs_array = sparse.csr_matrix(data)
        with open(npz_savepath, 'wb') as npzfile:
            sparse.save_npz(npzfile, sprs_array)

    def store_mask_array(self, array: np.ndarray):
        """ saves specified pixel mask array to npy file with the path COMMONPREFIX_mask.npy"""
        path = self._path_start + '_mask.npy'
        np.save(path, array)
        self._mask = array


    def store_affine_matrix(self, matrix: np.ndarray):
        """ saves specified affine transformation (camera to DMD) to npy file."""
        path = self._path_start + '_affine.npy'
        np.save(path, matrix)
        pass

    def _setup_store(self, path, uuid_str, extra_data=None):
        """ writes a json file specifying information about the run like uuid and data description
         This is only run once when the store is made. """
        store_dict = {'uuid': uuid_str,
                      'description': self._description}
        if extra_data is not None:
            for k, v in extra_data.items():
                store_dict[k] = v
        with open(path, 'w') as f:
            json.dump(store_dict, f)

    def _setup_framedata(self, fieldnames:list):
        """ sets up a framedata csv file using a DictWriter with the fieldnames specified.
        This must be done indpendently from the store setup, as it is """
        self._framedata_csv = csv.DictWriter(self._framedata_file, fieldnames)
        self._framedata_csv.writeheader()


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
