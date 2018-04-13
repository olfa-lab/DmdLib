import pytest
from staonline.io import pattern_loader
from dmdlib.randpatterns.saving import SparseSaver
import numpy as np
import os
from scipy import sparse


@pytest.fixture(scope='module')
def saver(tmpdir_factory):
    tmpdir = tmpdir_factory.mktemp('datastore')
    s = SparseSaver(tmpdir, 'integration_tst')
    s.store_mask_array(np.ones((100,110)))

    return s


def test_read(saver:SparseSaver):
    """ Test subsequent reads of one and multiple array saves. """
    dir = saver.savedir
    prefix = saver.prefix
    patternloader = pattern_loader.PatternLoader(dir, prefix)

    data_1 = np.random.randint(0, 2, (100,110))

    saver.store_sequence_array(data_1)
    saver.flush()

    reloaded = patternloader.get_next()  #type: pattern_loader.PatternData
    assert reloaded.frames.shape == data_1.shape
    assert np.all(reloaded.frames == data_1)

    data_multi = [np.random.randint(0, 2, (100,110)) for x in range(3)]


    concat = np.vstack(data_multi)

    for d in data_multi:
        saver.store_sequence_array(d)
    saver.flush()
    reloaded2 = patternloader.get_next()
    assert np.all(reloaded2.frames == concat)


def test_groupswitch(saver:SparseSaver):
    """
    Tests that we follow to the next group (ie transition from aaa to aab).
    """

    dir = saver.savedir
    prefix = saver.prefix
    patternloader = pattern_loader.PatternLoader(dir, prefix)

    _ = patternloader.get_next()

    data_1 = np.random.randint(0, 2, (100, 110))
    data_2 = np.random.randint(0, 2, (100, 110))
    data_3 = np.random.randint(0, 2, (100, 110))

    all_patterns = np.concatenate((data_1, data_2, data_3))
    saver.store_sequence_array(data_1)
    saver.iter_pattern_group()
    saver.store_sequence_array(data_2)
    saver.store_sequence_array(data_3)
    saver.flush()

    reloaded = patternloader.get_next()

    assert np.all(reloaded.frames == all_patterns)
