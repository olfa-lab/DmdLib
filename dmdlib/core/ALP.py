from __future__ import print_function
from ctypes import *
import ctypes
from ._alp_defns import *
import numpy as np
import time


def _api_call(function):
    """
    decorator to implement error handling for ALP API calls.
    """
    def api_handler(dmd_instance, *args, **kwargs):
        r = function(dmd_instance, *args, **kwargs)
        if r == ALP_ERROR_COMM or r == ALP_DEVICE_REMOVED:
            dmd_instance.connected = False
            r = dmd_instance._try_reconnect()
            if r == ALP_OK:  # try again.
                r = function(dmd_instance, *args, **kwargs)
        dmd_instance._handle_api_return(r)
        return r
    return api_handler


class AlpDmd:
    """
    Interface with Vialux ALP DMD API.
    """

    returnpointer = c_long()  # throwaway C pointer that is passed into functions and stores the return message
    alp_id = c_ulong()  # handle

    def __init__(self, verbose=False):
        self.connected = False  # is the device connected?
        self.temps = {'DDC': 0, 'APPS': 0, 'PCB': 0}  # temperatures in deg C
        self.seq_handles = []
        self._AlpDevAlloc()

        self.connected = True

        if self._get_device_status() == ALP_DMD_POWER_FLOAT:
            raise AlpError('Device is in low power float mode, check power supply.')

        self.ImWidth, self.ImHeight = self._get_device_size()
        self.w, self.h = self.ImWidth, self.ImHeight
        self.pixelsPerIm = self.ImHeight * self.ImWidth

        if verbose:
            print('Device image size is {} x {}.'.format(self.ImWidth, self.ImHeight))

        self._projecting = c_long()
        self._proj_progress = AlpProjProgress()

    def _try_reconnect(self):
        print('trying reconnect...')
        val = alp_cdll.AlpDevControl(self.alp_id, ALP_USB_CONNECTION, ALP_DEFAULT)
        if val == ALP_OK:
            self.connected = True
        return val

    def _handle_api_return(self, returnval):
        """
        Check for errorstates and raise python exceptions. Also update connection status.
        :param returnval:
        :return: True if connected
        """
        if returnval == ALP_OK:
            return True
        elif returnval == ALP_NOT_AVAILABLE:
            self.connected = False
            raise AlpError('ALP_NOT_AVAILABLE')
        elif returnval == ALP_NOT_IDLE:
            raise AlpError('ALP_NOT_IDLE')
        elif returnval == ALP_SEQ_IN_USE:
            raise AlpError('ALP_SEQ_IN_USE')
        elif returnval == ALP_PARM_INVALID:
            raise AlpError('ALP_PARM_INVALID')
        elif returnval == ALP_ADDR_INVALID:
            raise AlpError('ALP_ADDR_INVALID')
        elif returnval == ALP_DEVICE_REMOVED:
            self.connected = False
            raise AlpError('ALP_DEVICE_REMOVED')
        elif returnval == ALP_ERROR_POWER_DOWN:
            raise AlpError('ALP_ERROR_POWER_DOWN')
        elif returnval == ALP_ERROR_COMM:
            self.connected = False
            raise AlpError("ALP_ERROR_COMM")
        elif returnval == ALP_NOT_READY:
            self.connected = False
            raise AlpError("ALP_NOT_READY")
        else:
            raise AlpError('unknown error.')

    @_api_call
    def _AlpDevAlloc(self):
        return alp_cdll.AlpDevAlloc(ALP_DEFAULT, ALP_DEFAULT, byref(self.alp_id))

    @_api_call
    def _AlpDevInquire(self, inquire_type, uservarptr):
        # todo: check if uservarptr is a CArgObject.
        return alp_cdll.AlpDevInquire(self.alp_id, inquire_type, uservarptr)

    @_api_call
    def _AlpDevControl(self, control_type, control_value):
        return alp_cdll.AlpDevControl(self.alp_id, control_type, control_value)

    @_api_call
    def _AlpDevHalt(self):
        return alp_cdll.AlpDevHalt(self.alp_id)

    @_api_call
    def _AlpDevFree(self):
        return alp_cdll.AlpDevFree(self.alp_id)

    @_api_call
    def _AlpSeqAlloc(self, bitplanes, picnum, sequence_id_ptr):
        """
        Allocates memory for a specific number of frames (pictures) at a specific bit-depth. Writes a handle to pointer
        for referencing this sequence later.

        :param bitplanes: bit depth
        :param picnum:
        :param sequence_id_ptr:
        :return:
        """
        return alp_cdll.AlpSeqAlloc(self.alp_id, bitplanes, picnum, sequence_id_ptr)

    @_api_call
    def _AlpSeqControl(self, sequence_id, controltype, controlvalue):
        return alp_cdll.AlpSeqControl(self.alp_id, sequence_id, controltype, controlvalue)

    @_api_call
    def _AlpSeqTiming(self,
                      sequenceid,
                      illuminatetime=c_long(ALP_DEFAULT),
                      picturetime=c_long(ALP_DEFAULT),
                      syncdelay=c_long(ALP_DEFAULT),
                      syncpulsewidth=c_long(ALP_DEFAULT),
                      triggerindelay=c_long(ALP_DEFAULT)):
        """
        Use picturetime to specify time between consecutive pictures in us.

        :param sequence_id:
        :param illuminatetime: default gives highest possible contrast with specified picture time.
        :param picturetime: time between two consecutive pictures in microseconds (framerate) (default 33334)
        :param syncdelay: delay between frame sync output and start of display (master mode).
        :param syncpulsewidth: length of sync out pulse (master mode), by default pulse finishes at same time as illumination.
        """

        # todo: verify ctype in the low level API!
        return alp_cdll.AlpSeqTiming(self.alp_id, sequenceid, illuminatetime, picturetime,
                                     syncdelay, syncpulsewidth, triggerindelay)

    @_api_call
    def _AlpSeqInquire(self, sequenceid, inquiretype, uservarptr):
        return alp_cdll.AlpSeqInquire(self.alp_id, sequenceid, inquiretype, uservarptr)

    @_api_call
    def _AlpSeqPut(self, sequenceid, picoffset, n_pix, userarrayptr):
        """
        Loads image bytes into pre-allocated ALP memory (allocation using _AlpSeqAlloc)

        ** Blocking until sequence is loaded. **

        :param sequenceid: id of sequence (returned when sequence are allocated).
        :param picoffset: offset in pictures from which to load from the buffer (usually 0)
        :param n_pix: number of pics to load
        :param userarrayptr: C-order c_char array.
        :return:
        """
        return alp_cdll.AlpSeqPut(self.alp_id, sequenceid, picoffset, n_pix, userarrayptr)

    @_api_call
    def _AlpSeqFree(self, sequenceid):
        """
        :type sequenceid: c_long
        """
        return alp_cdll.AlpSeqFree(self.alp_id, sequenceid)

    @_api_call
    def _AlpProjControl(self, controltype, controlvalue):
        """
        :type controltype: c_long
        :type controlvalue: c_long
        """
        return alp_cdll.AlpProjControl(self.alp_id, controltype, controlvalue)

    @_api_call
    def _AlpProjInquire(self, inquire_type, uservarptr):
        return alp_cdll.AlpProjInquire(self.alp_id, inquire_type, uservarptr)

    @_api_call
    def _AlpProjInquireEx(self, inquire_type, userstructptr):
        """
        Retrieve progress information about active sequences and the sequence queue. The required data structure is
        AlpProjProgress. See also Inquire Progress of Active Sequences.

        :param inquire_type: ALP_PROJ_PROGRESS
        :param userstructptr: pointer to AlpProjProgress structure.
        """
        return alp_cdll.AlpProjInquireEx(self.alp_id, inquire_type, userstructptr)

    @_api_call
    def AlpProjStart(self, sequenceid):
        """
        Start projection of specified sequence. Returns immediately on call.

        'The sequence display can be stopped using _AlpProjHalt or _AlpDevHalt.'

        'A transition to the next sequence can take place without any gaps, if a sequence display is currently
        active. Depending on the start mode of the current sequence, the switch happens after the completion
        of the last repetition (controlled by ALP_SEQ_REPEAT, AlpProjStart), or after the completion of the
        current repetition (_AlpProjStartCont). Only one sequence start request can be queued. Further
        requests are replacing the currently waiting request.'

        :type sequenceid: c_long
        """
        return alp_cdll.AlpProjStart(self.alp_id, sequenceid)

    @_api_call
    def _AlpProjStartCont(self, sequenceid):
        """
        Start projection of specified sequence on continuous loop. Returns
        :type sequenceid: c_long
        :return:
        """
        return alp_cdll.AlpProjStartCont(self.alp_id, sequenceid)

    @_api_call
    def _AlpProjHalt(self):
        """
        halts projection of current sequence.
        """
        return alp_cdll.AlpProjHalt(self.alp_id)

    @_api_call
    def _AlpProjWait(self):
        """
        blocking call that returns only when projection is complete.
        """
        print ('Waiting for projection to complete...')
        return alp_cdll.AlpProjWait(self.alp_id)


    def _get_device_size(self):
        """
        :return:  tuple representing (width, height)
        """
        im_width, im_height = c_long(), c_long()
        self._AlpDevInquire(ALP_DEV_DISPLAY_WIDTH, byref(im_width))
        self._AlpDevInquire(ALP_DEV_DISPLAY_HEIGHT, byref(im_height))
        return im_width.value, im_height.value

    def _get_device_status(self):
        """
        gets device projection status and returns as an integer. (ie ALP_HALTED)
        :return:
        """
        val = c_long()
        self._AlpDevInquire(ALP_DEV_DMD_MODE, byref(val))
        return val.value

    #TODO: the block below needs work.
    def print_avail_memory(self):
        """
        prints available memory.
        """
        self._AlpDevInquire(ALP_AVAIL_MEMORY, byref(self.returnpointer))
        print("Remaining memory: " + str(self.returnpointer.value) + " / 43690 binary frames")

    def print_type(self):
        self._AlpDevInquire(ALP_DEV_DMDTYPE, byref(self.returnpointer))
        print("DMD Type: " + str(self.returnpointer.value))

    def print_memory(self):
        self._AlpDevInquire(ALP_AVAIL_MEMORY, byref(self.returnpointer));
        print("ALP memory: " + str(self.returnpointer.value))

    def print_projection(self):
        self._AlpProjInquire(ALP_PROJ_MODE, byref(self.returnpointer))
        print("ALP Projection Mode: " + str(self.returnpointer.value))

    @property
    def projecting(self):
        """
        Checks projection state. Returns 0 if not connected. Returns ALP_PROJ_STATE if projecting.
        :return:
        """
        if self.connected:
            self._AlpProjInquire(ALP_PROJ_STATE, byref(self._projecting))
            return self._projecting.value
        else:
            return 0

    def get_projecting_progress(self) -> AlpProjProgress:
        """
        Returns AlpProjProgress structure. See ALP API.

        AlpProjProgress(Structure):
	     _fields_ = [
            ("CurrentQueueId", c_ulong),
            ("SequenceId", c_ulong),
            ("nWaitingSequences", c_ulong),
            ("nSequenceCounter", c_ulong),
            ("nSequenceCounterUnderflow", c_ulong),
            ("nFrameCounter", c_ulong),
            ("nPictureTime", c_ulong),
            ("nFramesPerSubSequence", c_ulong),
            ("nFlags", c_ulong)
            ]
        :return: AlpProjProgress
        """
        # warning: not thread-safe, if we're reading values in one thread and reading in another!
        self._AlpProjInquireEx(ALP_PROJ_PROGRESS, byref(self._proj_progress))
        return self._proj_progress

    def update_temperature(self):
        """
        updates the object's temps dictionary.
        :return: None
        """
        self._AlpDevInquire(ALP_DDC_FPGA_TEMPERATURE, byref(self.returnpointer))
        self.temps['DDC'] = self.returnpointer.value / 256

        self._AlpDevInquire(ALP_APPS_FPGA_TEMPERATURE, byref(self.returnpointer))
        self.temps['APPS'] = self.returnpointer.value / 256

        self._AlpDevInquire(ALP_PCB_TEMPERATURE, byref(self.returnpointer))
        self.temps['PCB'] = self.returnpointer.value / 256

    def proj_mode(self, mode):
        """
        mode: single_TTL -- frames are advanced as long as input trigger is high. Sequence queue mode is also
        enabled, so that when one sequence ends, the next sequence starts with no lag. This enables the user to specify
        frames of different durations, uploading a different sequence for each frame. 
        (all frames within a sequence must be of the same duration).
        """
        alpmode = {'master':
                       ALP_MASTER,
                   'slave':
                       ALP_SLAVE,
                   'single_TTL':
                       ALP_MASTER,
                   'TTL_seqonset':
                       ALP_SLAVE
                   }

        if mode in alpmode:
            returnvalue = self._AlpProjControl(ALP_PROJ_MODE, alpmode[mode])
            # print('set PROJ_MODE: ' + mode + ' ' + str(returnvalue))

            if mode == 'TTL_seqonset':
                # sequence init upon TTL
                self.set_trigger_edge('rising')

                print(mode + str(returnvalue))

            if mode == 'single_TTL':
                # frames are advanced when TTL pulse is high, in sequence queue mode

                returnvalue = self._AlpProjControl(ALP_PROJ_STEP, ALP_LEVEL_HIGH)
                # step to next frame on rising TTL edge
                print('single_TTL: ' + str(returnvalue))

                self.seq_queue_mode()

        else:
            self.stop()
            self.shutdown()
            print("Desired mode is: " + "'" + str(mode) + "'")
            print("Available modes are: ")
            print(alpmode.keys())
            raise ValueError('Cannot set projector mode, shutting down...')

    def seq_alloc(self, bitnum:int, picnum:int) -> "AlpFrameSequence":
        """pre-allocate memory for sequence
        bitnum: bit-depth of sequence, e.g. '1L'
        picnum: # frames in sequence, e.g. '2L'
        
        returns AlpFrameSequence pointing to the allocated position.
        """
        seq_id = c_long()  # pointer to seq id

        returnvalue = self._AlpSeqAlloc(bitnum, picnum, byref(seq_id))
        if returnvalue == ALP_OK:
            seq = AlpFrameSequence(seq_id, bitnum, picnum, self)
            self.seq_handles.append(seq)
        return seq

    def seq_free(self, sequence: "AlpFrameSequence"):
        """free sequence (specify using handle) from memory """

        returnvalue = self._AlpSeqFree(sequence.seq_id)
        if returnvalue == ALP_OK:
            self.seq_handles.remove(sequence)
        if returnvalue == 1003:
            raise ValueError('Try DMD.stop() before attempting to release sequence')

    def seq_free_all(self):
        """clear all sequences from DMD"""
        for seq in self.seq_handles:
            self.seq_free(seq)

        self.seq_handles = []

    def _AlpSeqTimingseq_timing(self, sequence: "AlpFrameSequence", stimon_time, stimoff_time):
        """set sequence timing parameters (Master Mode)
        stimon_time e.g. 800000L (microseconds)
        stimoff_time e.g. 200000L
        """

        PictureTime = stimon_time + stimoff_time  # ALP-4.2: time between consecutive stim onsets
        returnvalue = self._AlpSeqTiming(sequence.seq_id, stimon_time, PictureTime, c_long(0), ALP_DEFAULT, ALP_DEFAULT)

    def seq_start(self, sequence):
        returnvalue = self.AlpProjStart(sequence)
        # print 'seq_start: ' + str(returnvalue)

    def seq_start_loop(self, sequence):
        returnvalue = self._AlpProjStartCont(sequence)

    def seq_queue_mode(self):
        returnvalue = self._AlpProjControl(ALP_PROJ_QUEUE_MODE, ALP_PROJ_SEQUENCE_QUEUE)
        # print 'Sequence queue set with : ' + str(returnvalue)

    def set_trigger_edge(self, edge_type):
        alp_edge_type = {'rising':
                             ALP_EDGE_RISING,
                         'falling':
                             ALP_EDGE_FALLING
                         }

        if edge_type in alp_edge_type:
            alp_trigger_value = alp_edge_type[edge_type]
            returnvalue = self._AlpDevControl(ALP_TRIGGER_EDGE, alp_trigger_value)
            print(edge_type + ' trigger set with value: ' + str(returnvalue))

        else:
            self.stop()
            self.shutdown()
            print("Desired trigger is: " + "'" + str(edge_type) + "'")
            print("Available modes are: ")
            print(alp_edge_type.keys())
            raise ValueError('Cannot set trigger edge , shutting down...')

    def make_sequence_array(self, n_pix=1):
        """ make an array to hold n_pix number of frames.
        :param n_pix: number of images (frames) in the sequence.
        :return: numpy uint8 array (n, h, w)
        """
        return np.zeros((n_pix, self.h, self.w), dtype='uint8')

    def stop(self):
        if self.connected:
            returnvalue = self._AlpDevHalt()
        # print('seq_stop: ' + str(returnvalue))

    def shutdown(self):
        if self.connected:
            returnvalue = self._AlpDevFree()
            self.connected = False
        # print('Shutdown value: ' + str(returnvalue))
        
    def __enter__(self): return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        print ('DMD shutting down...', end='')
        self.stop()
        self.shutdown()
        print('complete.')

    def __del__(self):
        self.stop()
        self.shutdown()


class AlpFrameSequence:
    """
    Interface with allocated ALP frame sequence buffer. Allows for upload to the memory slot, destruction of the
    allocation, and projection start of an uploaded frame sequence.
    """
    def __init__(self, seq_id: c_long, bitnum, picnum, parent: AlpDmd):
        """

        :param seq_id:
        :param bitnum: bit depth of the allocated sequence
        :param picnum:
        """

        self.seq_id = seq_id
        self.bitnum = bitnum
        self.picnum = picnum
        self._parent = parent
        self.w = parent.w
        self.h = parent.h
        self.illuminatetime = -1
        self.picturetime = -1
        self.syncdelay = -1
        self.syncpulsewidth = -1
        self.triggerindelay = -1
        self.array = self.gen_array()


    def set_timing(self, illuminatetime=c_long(ALP_DEFAULT),
                      picturetime=c_long(ALP_DEFAULT),
                      syncdelay=c_long(ALP_DEFAULT),
                      syncpulsewidth=c_long(ALP_DEFAULT),
                      triggerindelay=c_long(ALP_DEFAULT)):

        self._parent._AlpSeqTiming(self.seq_id, illuminatetime, picturetime, syncdelay, syncpulsewidth,
                                   triggerindelay)

        self.illuminatetime = illuminatetime
        self.picturetime = picturetime
        self.syncdelay = syncdelay
        self.syncpulsewidth = syncpulsewidth
        self.triggerindelay = triggerindelay

    def gen_array(self):
        return np.zeros((self.picnum, self._parent.h, self._parent.w), dtype='uint8')

    def upload_array(self, pattern=None):
        """
        Uploads a numpy uint8 array pattern to parent DMD into this sequence space. This handles the sequence
        shape definition based on what was allocated, and it handles conversion from numpy array to a C
        pointer of chars.

        :param pattern: numpy array of uint8 values to be uploaded.
        """

        if pattern is not None:
            # assert pattern.dtype == np.uint8
            # assert pattern.shape == self.array.shape
            self.array[:, :, :] = pattern[:, :, :]

        patternptr = self.array.ctypes.data_as(POINTER(c_char))
        self._parent._AlpSeqPut(self.seq_id,  c_long(0), c_long(self.picnum), patternptr)

    def start_projection(self):
        self._parent.AlpProjStart(self.seq_id)

    def __lt__(self, other):
        # For sorting.
        assert isinstance(other, AlpFrameSequence)
        return self.seq_id.value < other.seq_id.value

    def __int__(self):
        return self.seq_id.value

    def __del__(self):
        if self._parent.connected:
            self._parent.seq_free(self)

    def __str__(self):
        return 'Sequence {}'.format(self.seq_id.value)


# ERROR HANDLING STUFF:


class AlpError(Exception):
    pass

class AlpDisconnectError(AlpError):
    pass

class AlpOutOfMemoryError(AlpError):
    pass



try:
    alp_cdll = CDLL('alpV42.dll')
except WindowsError as e:
    raise AlpError("The directory containing 'alpV42.dll' is not found in the system (Windows) path. "
                   "Please add it to use this package.")


def powertest(edge_sz_px=160):
    # import matplotlib.pyplot as plt
    """
    turns on pixels in a square with specified edge length. This is useful for displaying a 1 mm x 1 mm square for
    power calibration.

    This

    :param edge_sz_px:
    :return:
    """
    with AlpDmd() as dmd:  # context handles shutdown.
        dmd.seq_queue_mode()
        dmd.proj_mode('master')
        seq_id = c_long()
        dmd._AlpSeqAlloc(c_long(1), c_long(1), byref(seq_id))
        dmd._AlpSeqControl(seq_id, ALP_BIN_MODE, ALP_BIN_UNINTERRUPTED)
        dmd._AlpSeqTiming(seq_id)

        seq_array = np.zeros((dmd.h, dmd.w), 'uint8')
        center_x, center_y = [x//2 for x in (dmd.w, dmd.h)]
        st_x, st_y = [x - edge_sz_px // 2 for x in (center_x, center_y)]
        nd_x, nd_y = [x - (-edge_sz_px // 2) for x in (center_x, center_y)]
        seq_array[st_y:nd_y, st_x:nd_x] = 255
        # plt.imshow(seq_array); plt.show()
        # print(seq_array.sum()/255.)

        dmd._AlpSeqPut(seq_id, c_long(0), c_long(1), seq_array.ctypes.data_as(POINTER(c_char)))
        dmd._AlpProjStartCont(seq_id)
        input("Press Enter key to end...")



def disp_affine_pattern(coords=([450, 300], [550, 275], [500, 430])):
    # import matplotlib.pyplot as plt
    dmd, seq_id = init_static_dmd()
    seq_arr = dmd.make_sequence_array()
    print(seq_arr.shape)
    for c in coords:
        x, y = c
        seq_arr[0, y, x] = 255  # seq array is h, w indexed.

    dmd._AlpSeqPut(seq_id, c_long(0), c_long(1), seq_arr.ctypes.data_as(POINTER(c_char)))
    dmd._AlpProjStartCont(seq_id)
    # plt.imshow(seq_arr[0,:,:]); plt.show()

    input("Press Enter key to end...")
    dmd._AlpProjHalt()
    dmd.shutdown()
    return coords


def disp_image_pattern(img: np.ndarray, dmd=None):
    assert img.dtype == np.uint8
    dmd, seq_id = init_static_dmd()
    if img.shape == (dmd.h, dmd.w):
        dmd._AlpSeqPut(seq_id, c_long(0), c_long(1), img.ctypes.data_as(POINTER(c_char)))
        dmd._AlpProjStartCont(seq_id)
        input('Press Enter key to end...')
        dmd._AlpProjHalt()
    dmd.shutdown()
    return


def init_static_dmd() -> (AlpDmd, c_long):
    """initialize dmd for static (continuous) display of single image.

    :return: c_long seq_id for upload later.
    """
    dmd = AlpDmd()
    dmd.seq_queue_mode()
    dmd.proj_mode('master')
    seq_id = c_long()
    dmd._AlpSeqAlloc(c_long(1), c_long(1), byref(seq_id))
    dmd._AlpSeqControl(seq_id, ALP_BIN_MODE, ALP_BIN_UNINTERRUPTED)
    dmd._AlpSeqTiming(seq_id)

    return dmd, seq_id
