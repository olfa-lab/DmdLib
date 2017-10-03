from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import sys
from dmdlib.mask_maker.image_load import *
import pickle
import cv2
import json
try:
    from dmdlib import ALP
except:
    pass

from ctypes import c_long, byref, POINTER, c_char

TRANSFORM_CONFIG_PATH_KEY = 'cam_to_dmd'
IMAGE_CONFIG_PATH_KEY = 'img_path'


class MyMainWindow(QMainWindow):

    def closeEvent(self, event: QCloseEvent):
        print('close')
        if not self.centralWidget()._saved:
            save_dialog = QMessageBox(self)

            if self.centralWidget()._mask_ready:
                save_dialog.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            else:
                save_dialog.setStandardButtons(QMessageBox.Close | QMessageBox.Cancel)
            save_dialog.setWindowTitle('Exit?')
            save_dialog.setText('A mask has not been saved.')
            save_dialog.setInformativeText('Do you really want to exit?')
            save_dialog.setDefaultButton(QMessageBox.Save)
            save_dialog.setEscapeButton(QMessageBox.Cancel)
            result = save_dialog.exec()
            if result == QMessageBox.Save:
                self.centralWidget().save_mask()
                event.accept()
            elif result == QMessageBox.Cancel:
                event.ignore()
            elif result == QMessageBox.Discard or result == QMessageBox.Close:
                event.accept()
        else:
            event.accept()


class MainWidget(QWidget):
    transformLoaded = pyqtSignal(bool)
    imageLoaded = pyqtSignal(QImage)
    maskRegistered = pyqtSignal(bool)

    def __init__(self):
        super(MainWidget, self).__init__()
        self._cwd = None
        layout = QHBoxLayout()
        self.controlwidget = ControlWidget(self)
        self.imwidget = ImageWidget(self)
        layout.addWidget(self.controlwidget)
        layout.addWidget(self.imwidget)
        self.setLayout(layout)
        self.config = get_config()
        self.cam_to_dmd_transform = None
        try:
            self.dmd = self.connect_dmd()
        except Exception as e:
            self.dmd = None
            err = QErrorMessage(self)
            err.showMessage("DMD not connected. {}".format(e))
        self.dmd_mask = None
        # update the displayed image when we successfully load an image.
        self.imageLoaded.connect(self.imwidget.set_image)
        self.cam_to_dmd_transform = None
        self.controlwidget.load_image_button.clicked.connect(self.load_image)
        self.controlwidget.load_transform_button.clicked.connect(self.load_transform)
        self.controlwidget.zoombutton.clicked.connect(self.imwidget.zoomin)
        self.controlwidget.zoomoutbutton.clicked.connect(self.imwidget.zoomout)
        self.controlwidget.mask_calc_button.clicked.connect(self.imwidget.calc_mask)
        self.controlwidget.mask_save_button.clicked.connect(self.save_mask)
        self.controlwidget.mask_disp_button.clicked.connect(self.disp_mask)
        self.controlwidget.mask_disp_stop_button.clicked.connect(self.disp_stop)
        self.controlwidget.mask_clear_button.clicked.connect(self.imwidget.clear_mask_poly)
        self.imwidget.mask_generated.connect(self.register_mask)
        self.transformLoaded.connect(self.controlwidget.mask_calc_button.setEnabled)
        self.maskRegistered.connect(self.controlwidget.mask_disp_button.setEnabled)  # enable when mask is actually available for display.
        self.maskRegistered.connect(self.controlwidget.mask_disp_stop_button.setEnabled)
        self.maskRegistered.connect(self.controlwidget.mask_save_button.setEnabled)
        try:
            if TRANSFORM_CONFIG_PATH_KEY in self.config.keys() and os.path.exists(self.config[TRANSFORM_CONFIG_PATH_KEY]):
                self.load_transform(self.config[TRANSFORM_CONFIG_PATH_KEY])
        except:
            pass
        self._saved = False
        self._mask_ready = False

    @pyqtSlot()
    def load_transform(self, filepath=None):
        startpath = None
        try:
            if TRANSFORM_CONFIG_PATH_KEY in self.config.keys() and os.path.exists(self.config[TRANSFORM_CONFIG_PATH_KEY]):
                filepath = self.config[TRANSFORM_CONFIG_PATH_KEY]

        except:
            pass
        self.transformLoaded.emit(False)
        d = None
        if filepath is None:
            d = QFileDialog()
            if startpath:
                d.setDirectory(startpath)
            d.setFileMode(QFileDialog.ExistingFile)
            d.setNameFilter("Transform file (*.pickle)")
            d.show()
            if d is not None and d.exec_():
                filepath = d.selectedFiles()[0]
        if filepath is not None:
            try:
                with open(filepath, 'rb') as f:
                    transform_dict = pickle.load(f)
                    print("transform loaded at {}".format(filepath))
                    self.cam_to_dmd_transform = transform_dict['cam_to_dmd']
                    self.transformLoaded.emit(True)
                    self.config[TRANSFORM_CONFIG_PATH_KEY] = filepath
                    save_config(self.config)
            except:
                #todo: error msg.
                pass

    @pyqtSlot(np.ndarray)
    def register_mask(self, cam_array, ):
        try:
            dmd_shape = self.dmd.w, self.dmd.h  # this is opposite of what you would expect because cv2 returns transposed matrix.
            self.dmd_mask = cv2.warpAffine(cam_array.astype('uint8'), self.cam_to_dmd_transform, dmd_shape) # return shape (h, w)
            self.maskRegistered.emit(True)
            self._mask_ready = True
        except:
            self.maskRegistered.emit(False)
            self.dmd_mask = None
            self._mask_ready = False

    @pyqtSlot()
    def disp_mask(self):
        if self.dmd is None:
            newwidget = QWidget()
            h, w = self.dmd_mask.shape
            img = QImage(self.dmd_mask.data, w, h, QImage.Format_Mono)
            label = QLabel(newwidget)
            label.setPixmap(QPixmap.fromImage(img))
            newwidget.show()
        else:
            seq = self.dmd_mask.astype('uint8')
            seq *= 255
            seqpointer = seq.ctypes.data_as(POINTER(c_char))
            seq_id = c_long()
            self.dmd.AlpSeqAlloc(c_long(1), c_long(1), byref(seq_id))
            self.dmd.AlpSeqPut(seq_id, c_long(0), c_long(1), seqpointer)
            self.dmd.AlpProjStartCont(seq_id)
        return

    @pyqtSlot()
    def disp_stop(self):
        self.dmd.AlpProjHalt()

    def connect_dmd(self):
        """
        This can be generalized to other dmd architectures (ie mightex).

        :return:
        """
        dmd, seq_id = ALP.init_static_dmd()
        return dmd

    @pyqtSlot()
    def load_image(self):
        """
        opens file dialog and emits "image_loaded signal" image

        :param startpath: Path to start dialog in.
        :param filepath: Force loading a specific file without opening the file dialog.
        :return: none
        """
        startpath = None
        if self._cwd:
            startpath = self._cwd
        else:
            try:
                if IMAGE_CONFIG_PATH_KEY in self.config.keys():
                    # print(self.config[IMAGE_CONFIG_PATH_KEY])
                    startpath, _ = os.path.split(self.config[IMAGE_CONFIG_PATH_KEY])
                    # print(startpath)
            except:
                pass
        filepath = None

        d = None
        if filepath is None:
            d = QFileDialog()
            if startpath:
                d.setDirectory(startpath)
            d.setFileMode(QFileDialog.ExistingFile)
            d.setNameFilter("Images (*.tsm, *.tiff, *.tif)")
            d.show()
        if d is not None and d.exec_():
            filepath = d.selectedFiles()[0]
            self._cwd, _ = os.path.split(filepath)
        if filepath is not None:
            _, ext = os.path.splitext(filepath)
            loader = image_loaders[ext]
            img = loader(filepath)
            self.imageLoaded.emit(img)
            self.config[IMAGE_CONFIG_PATH_KEY] = filepath
            save_config(self.config)
        return

    @pyqtSlot()
    def save_mask(self):
        filepath = None
        d = QFileDialog()
        # print(self._cwd)
        if self._cwd:
            d.setDirectory(self._cwd)
        d.setWindowTitle('Save mask')
        d.setFileMode(QFileDialog.AnyFile)
        d.setNameFilter('mask files (*.npy)')
        d.show()
        if d is not None and d.exec_():
            filepath = d.selectedFiles()[0]
            self._cwd, _ = os.path.split(filepath)
        # print(self.dmd_mask.shape)
        if filepath is not None:
            if not filepath.endswith('.npy'):
                if not filepath.endswith(os.path.extsep):
                    filepath = filepath + os.path.extsep
                filepath = filepath + 'npy'
            self.config['LAST_MASK_SAVED'] = filepath
            np.save(filepath, self.dmd_mask.astype('bool'))
            self._saved = True



class ControlWidget(QWidget):

    def __init__(self, parent=None):
        super(ControlWidget, self).__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)
        layout = QVBoxLayout()
        self.load_image_button = QPushButton("Load image...", self)
        self.load_transform_button = QPushButton('Load affine transform file...', self)

        layout.addWidget(self.load_image_button)
        layout.addWidget(self.load_transform_button)

        self.show_grid_button = QPushButton('Show &grid', self)
        self.show_grid_button.setCheckable(True)
        self.show_grid_button.toggled.connect(parent.update)
        layout.addWidget(self.show_grid_button)
        # self.toolselector = ToolSelector(self)
        # layout.addWidget(self.toolselector)
        layout.addStretch()

        self.mask_calc_button = QPushButton('Calculate mask', self)
        self.mask_calc_button.setEnabled(False)
        self.mask_save_button = QPushButton('Save mask...', self)
        self.mask_save_button.setEnabled(False)
        self.mask_clear_button = QPushButton('Clear mask', self)
        layout.addWidget(self.mask_calc_button)
        layout.addWidget(self.mask_save_button)
        layout.addWidget(self.mask_clear_button)

        mask_disp_box = QGroupBox(self)
        mask_disp_box.setTitle('Mask display on DMD')
        self.mask_disp_button = QPushButton('Start', mask_disp_box)
        self.mask_disp_button.setEnabled(False)
        self.mask_disp_stop_button = QPushButton('Stop', mask_disp_box)
        self.mask_disp_stop_button.setEnabled(False)
        disp_layout = QHBoxLayout(mask_disp_box)
        disp_layout.addWidget(self.mask_disp_button)
        disp_layout.addWidget(self.mask_disp_stop_button)
        layout.addWidget(mask_disp_box)

        zoom_box = QGroupBox(self)
        zoom_box.setTitle('Zoom')
        self.zoombutton = QPushButton('in', zoom_box)
        self.zoomoutbutton = QPushButton('out', zoom_box)
        zoom_layout = QHBoxLayout(zoom_box)
        zoom_layout.addWidget(self.zoombutton)
        zoom_layout.addWidget(self.zoomoutbutton)
        layout.addWidget(zoom_box)

        self.setMinimumSize(layout.sizeHint())
        self.setLayout(layout)


class ToolSelector(QGroupBox):
    TOOLS = ('Draw &exclusion area polygon', "Draw &points", "Draw poly&gon")
    changed_sig = pyqtSignal(int)

    def __init__(self, parent, *args, **kwargs):
        super(ToolSelector, self).__init__(parent)
        self.setTitle('Tool Selector')
        self.buttongroup = QButtonGroup(self)
        layout = QVBoxLayout(self)
        _button_types = self.TOOLS
        for i, t in enumerate(_button_types):
            b = QRadioButton(t, self)
            self.buttongroup.addButton(b, i)
            layout.addWidget(b)
        self.setLayout(layout)
        self.buttongroup.buttonClicked[int].connect(self._tool_selected)

    @pyqtSlot(int)
    def _tool_selected(self, b):
        self.changed_sig.emit(b)


class ImageWidget(QGraphicsView):

    # imageLoaded = pyqtSignal(str)
    mask_generated = pyqtSignal(np.ndarray)

    def __init__(self, parent):
        super(ImageWidget, self).__init__(parent)
        self.setScene(QGraphicsScene())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_pixmap = QGraphicsPixmapItem(QPixmap(1000,1000))
        self.setMinimumSize(QSize(256 * 3.5, 256 * 2.5))
        self.scene().addItem(self.image_pixmap)
        # self.scene().addRect(100, 0, 80, 100, QPen(Qt.black), QBrush(Qt.blue))
        self.polypen = QPen()
        self.polypen.setWidth(2)
        red70 = QColor(Qt.red)
        red70.setAlphaF(.7)
        self.polypen.setColor(red70)
        self.polygon = self.scene().addPolygon(QPolygonF(), self.polypen)  # todo: add pen and other formatting items.
        nullsz = 500
        self.polygon_mask = np.zeros([1, 1], bool)
        img = QImage(np.random.randint(0, 255, nullsz**2).astype('uint8'), nullsz, nullsz, QImage.Format_Grayscale8)
        self.set_image(img)
        self.control = parent.controlwidget

    @pyqtSlot(QImage)
    def set_image(self, img):
        pm = QPixmap.fromImage(img)
        self.im_shape = (img.height(), img.width(),)
        self.image_pixmap.setPixmap(pm)
        self.update()

    @pyqtSlot()
    def calc_mask(self):

        if len(self.polygon.polygon()) < 3:
            print('This polygon has no area!!!')
            return
        polygon_mask = np.zeros(self.im_shape, dtype=bool)
        # print(polygon_mask.shape)
        progress = QProgressDialog()
        progress.setWindowModality(Qt.WindowModal)
        progress.setLabelText('Calculating mask...')
        progress.setMinimum(0)
        progress.show()
        i = 0  # counter for progress bar
        p = QPoint(0, 0)

        br = self.polygon.boundingRect()  # we only need to iterate within the rectangle containing our polygon.
        st_x = int(br.x())  # floor is good here.
        st_y = int(br.y())
        nd_x = st_x + int(np.ceil(br.width()))  # need to ceil so that we get the last fractional pixel.
        nd_y = st_y + int(np.ceil(br.height()))
        n_iters = (nd_x - st_x) * (nd_y - st_y)
        progress.setMaximum(n_iters)

        for x in range(st_x, nd_x):
            for y in range(st_y, nd_y):
                p.setX(x)
                p.setY(y)
                polygon_mask[y, x] = self.polygon.contains(p)
                # It isn't completely trivial that this should work, but it does:
                # The QGraphicsPixMapItem is always painted starting at the scene's (0,0) point, and this
                # origin doesn't change if, for example, another item is added to a point that is negative to
                # the origin. Also, since the pixmap is scaled to 1 (even if the sceneview is zoomed
                # differently 1 px in scene coordinates is 1 px in pixmap coordinates. So using the coordinate
                # system of our mask bitmap, we're traverse the test point over the entire image pixmap area.
                # And since the QPolygon is in scene coordinates too, everything works.
                i += 1
                if not i % 500:
                    progress.setValue(i)
        self.mask_generated.emit(polygon_mask)

    @pyqtSlot()
    def zoomin(self):
        self.scale(1.5, 1.5)

    @pyqtSlot()
    def zoomout(self):
        self.scale(.75, .75)

    def mousePressEvent(self, e: QMouseEvent):
        pg = self.polygon.polygon()
        # print(self.mapToScene(e.pos()))
        pg.append(self.mapToScene(e.pos()))
        self.polygon.setPolygon(pg)

        return

    @pyqtSlot()
    def clear_mask_poly(self):
        self.polygon.setPolygon(QPolygonF())
        return

    def keyPressEvent(self, e: QKeyEvent):
        if e.modifiers():
            if e.modifiers() == Qt.ControlModifier and e.key() == Qt.Key_Z:
                self.undo()

    def undo(self):
        poly = self.polygon.polygon()  # type: QPolygonF
        if not poly.isEmpty():
            i = poly.count() - 1
            poly.remove(i)
        self.polygon.setPolygon(poly)



def main():
    app = QApplication(sys.argv)
    w = MyMainWindow()
    w.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
    mainwidget = MainWidget()
    w.setCentralWidget(mainwidget)
    w.show()
    sys.exit(app.exec_())


def config_path():
    if os.name == 'nt':
        appdataroot = os.environ['APPDATA']
        appdatapath = os.path.join(appdataroot, 'dmdlib')
    else:  # assume posix
        appdataroot = os.path.expanduser('~')
        appdatapath = os.path.join(appdataroot, '.dmdlib')
    return os.path.join(appdatapath, 'mask_maker_config.json')


def get_config():
    try:
        with open(config_path(), 'r+') as f:
            c = json.load(f)
    except:
        c = {}
    return c

def save_config(save_dict):
    with open(config_path(), 'w') as f:
        json.dump(save_dict, f)
    return


if __name__ == "__main__":
    main()
