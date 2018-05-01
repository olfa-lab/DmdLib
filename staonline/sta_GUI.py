from __future__ import unicode_literals
import sys
import os
import random
import matplotlib
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')
from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from staonline import main
# from staonline.io import pattern_loader, spike_extractor, storage
progname = os.path.basename(sys.argv[0])

class MyMplCanvas(FigureCanvas):
    """Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.)."""

    def __init__(self, maskpath, datpath, framespath, prefix, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        self.axes.axis('off')
        self.msk = np.load(maskpath)
        self.store = main.storage.DatReader(datpath)
        self.se = main.spike_extractor.SpikeExtractor(self.store, 3.5)
        self.patternloader = main.pattern_loader.PatternLoader(framespath, prefix)
        self.sta = main.StaMaker(self.se, self.patternloader)

        FigureCanvas.__init__(self, fig)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(self,
                                   QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)

class MyDynamicMplCanvas(MyMplCanvas):
    """A canvas that updates itself every second with a new plot."""

    def __init__(self, *args, **kwargs):
        MyMplCanvas.__init__(self, *args, **kwargs)
        timer = QtCore.QTimer(self)
        timer.timeout.connect(self.update_figure)
        timer.start(1000)

    def update_figure(self):
        self.axes.cla()
        self.sta.update()
        img = np.zeros(self.msk.shape)
        img[self.msk] = self.sta.sta
        self.axes.imshow(img, vmin = np.min(self.sta.sta))
        self.axes.axis('off')
        self.draw()


class ApplicationWindow(QtWidgets.QMainWindow):
    def __init__(self, maskpath, datpath, framespath, prefix):
        QtWidgets.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle("application main window")

        self.file_menu = QtWidgets.QMenu('&File', self)
        self.file_menu.addAction('&Quit', self.fileQuit,
                                 QtCore.Qt.CTRL + QtCore.Qt.Key_Q)
        self.menuBar().addMenu(self.file_menu)

        self.help_menu = QtWidgets.QMenu('&Help', self)
        self.menuBar().addSeparator()
        self.menuBar().addMenu(self.help_menu)

        self.main_widget = QtWidgets.QWidget(self)

        l = QtWidgets.QVBoxLayout(self.main_widget)
        self.dc = MyDynamicMplCanvas(self.main_widget, maskpath, datpath, framespath, prefix)
        l.addWidget(self.dc)

        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

    def fileQuit(self):
        self.close()

    def closeEvent(self, ce):
        np.save('sta_array', self.dc.sta.sta)
        self.fileQuit()

if __name__ == '__main__':
    qApp = QtWidgets.QApplication(sys.argv)
    maskpath = ''
    datpath = ''
    framepath = ''
    frame_prefix = ''
    aw = ApplicationWindow(maskpath,datpath,framepath,frame_prefix)
    aw.setWindowTitle("%s" % progname)
    aw.show()
    sys.exit(qApp.exec_())

