from __future__ import division
from PIL import Image, ImageFont
import numpy as np
import numba

font = ImageFont.load_default()


def make_text_img(text, margins=(10, 10, 150, 150), width=1028, height=684):
    """
    Draws a bitmap representing input text.

    :param text: text to draw
    :param margins: top, bottom, left, right
    :param width: width of returned image in px
    :param height: height of returned image in px
    :return: PIL Image object.
    """
    W, H = width, height
    image = Image.new("L", (W, H))
    impix = image.load()
    mask = font.getmask(text)
    mW, mH = mask.size
    top, bottom, left, right = margins
    W_margins = W - right - left
    H_margins = H - top - bottom
    W_scale = np.ceil(W_margins / mW)
    H_scale = np.ceil(H_margins / mH)

    for x in range(W_margins):
        x_mask = int((x / W_scale))
        for y in range(H_margins):
            y_mask = int((y / H_scale))
            maskv = mask.getpixel((x_mask, y_mask))
            if maskv:
                impix[x + left, y + top] = 1
    return image

def make_text_fast(text, array, margins=(10, 10, 150, 150), width=1028, height=684):
    mask = font.getmask(text)
    mask_array = np.asarray(mask, dtype=bool)
    mask_array.shape = mask.size[1], mask.size[0]
    top, bottom, left, right = margins
    _array_maker(array, mask_array, top, bottom, left, right, width, height)
    return

@numba.jit(nopython=True, parallel=True)
def _array_maker(arrayout, arrayin, top, bottom, left, right, width, height):
    W_margins = width - right - left
    H_margins = height - top - bottom
    mH, mW = arrayin.shape
    W_scale = int(np.ceil(W_margins / mW))
    H_scale = int(np.ceil(H_margins / mH))

    for x in range(W_margins):
        x_mask = x // W_scale
        for y in range(H_margins):
            y_mask = y // H_scale
            maskv = arrayin[y_mask, x_mask]
            arrayout[y+top, x+left] = maskv
    return


def make_text_array(text, margins=(10, 10, 150, 150), width=1028, height=684):
    """

    :param text: text to draw
    :param margins: top, bottom, left, right
    :param width: width of returned image in px
    :param height: height of returned image in px
    :return: numpy ndarray
    """
    img = make_text_img(text, margins, width, height)
    array = np.array(img)
    array.shape = (height, width)
    return array


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    img = make_text_fast("10")
    plt.imshow(img, interpolation='none')
    plt.show()
    print(img.shape)

    # arr = make_text_array("99")
    # print (arr.dtype)
