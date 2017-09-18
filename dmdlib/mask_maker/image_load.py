from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import numpy as np
import os
from PIL import Image

"""
It is possible to add image loaders that return a bitmap images. Add the functions to the image_loaders
dictionary with their extension as a key.
"""


def load_tsm(path, startframe=0, endframe=0):
    """
    Loads tsm images from RedShirt Imaging and returns the composite mean image within the file.

    You can also specify start and end frames to use to build the composite (eg you have a recording
    in which there are pre and post stimulus onset conditions.

    Adapted from JK.

    :param path: filepath
    :param startframe: first frame to include in the average
    :param endframe: last frame to include in output.
    :return:
    """

    HOFFSET = 2880  # this is hardcoded

    with open(path, 'rb') as f:
        header = f.read(HOFFSET)
        pixels = np.frombuffer(f.read(), 'uint16')
        header = [header[i:i + 80] for i in range(0, len(header), 80)]
        # remove all whitespaces
    for i, h in enumerate(header):
        header[i] = h.replace(b' ', b'')
    for h in header:
        if h == b'END':
            break
        else:
            param, value = h.split(b'=')
        if param == b'NAXIS1':
            width = int(value)
        elif param == b'NAXIS2':
            height = int(value)
        elif param == b'NAXIS3':
            n_frames = int(value)
        else:
            pass

    n_pixels = width * height
    trialframes = []

    if not endframe:
        endframe = n_frames

    for i_frame in range(startframe, endframe):
        st = i_frame * n_pixels
        nd = st + n_pixels
        frame = pixels[st:nd]
        frame.shape = width, height
        trialframes.append(frame)
    m = np.mean(trialframes, axis=0)
    scale = 255. / m.max()
    m_8 = m * scale
    img = QImage(m_8.astype('uint8').data, width, height, QImage.Format_Grayscale8)
    return img


def load_tiff(path):
    im = Image.open(path)  # type: Image.Image
    im_L = im.convert('L')
    arr = np.array(im_L)
    return QImage(arr.astype('uint8').data, im.width, im.height, QImage.Format_Grayscale8)


image_loaders = {
        '.tsm': load_tsm,
        '.tif': load_tiff,
        '.tiff': load_tiff
    }