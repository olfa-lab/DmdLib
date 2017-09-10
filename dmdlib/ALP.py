from ctypes import *
import ctypes
from ._alp_defns import *
import numpy as np
import time


class DMD(object):
    returnpointer = c_long()  # throwaway C pointer that is passed into functions and stores the return message
    alp_id = c_ulong()  # handle

    def __init__(self, verbose=True):
        self.connected = False  # is the device connected?
        self.temps = {'DDC': 0, 'APPS': 0, 'PCB': 0}  # temperatures in deg C
        self.seq_handles = []

        returnvalue = alp_cdll.AlpDevAlloc(ALP_DEFAULT, ALP_DEFAULT, byref(self.alp_id))
        if verbose:
            print 'Init value: ' + str(returnvalue)
        self._handle_api_return(returnvalue)
        self.connected = True

        if self._get_device_status() == ALP_DMD_POWER_FLOAT:
            raise AlpError('Device is in low power float mode, check power supply.')

        self.ImWidth, self.ImHeight = self._get_device_size()
        self.pixelsPerIm = self.ImHeight * self.ImWidth
        if verbose:
            print 'Device image size is {} x {}.'.format(self.ImWidth, self.ImHeight)

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
            # todo: reconnect to a error_comm call
        else:
            raise AlpError('unknown error.')





    def _get_device_size(self):
        im_width, im_height = c_long(), c_long()
        self._handle_api_return(alp_cdll.AlpDevInquire(self.alp_id, ALP_DEV_DISPLAY_WIDTH, byref(im_width)))
        self._handle_api_return(alp_cdll.AlpDevInquire(self.alp_id, ALP_DEV_DISPLAY_HEIGHT, byref(im_height)))
        return im_width.value, im_height.value

    def _get_device_status(self):
        val = c_long()
        self._handle_api_return(alp_cdll.AlpDevInquire(self.alp_id, ALP_DEV_DMD_MODE, byref(val)))
        return val.value

    def avail_memory(self):
        alp_cdll.AlpDevInquire(self.alp_id, ALP_AVAIL_MEMORY, byref(self.returnpointer))
        print "Remaining memory: " + str(self.returnpointer.value) + " / 43690 binary frames"

    def type(self):
        alp_cdll.AlpDevInquire(self.alp_id, ALP_DEV_DMDTYPE, byref(self.returnpointer))
        print "DMD Type: " + str(self.returnpointer.value)

    def memory(self):
        alp_cdll.AlpDevInquire(self.alp_id, ALP_AVAIL_MEMORY, byref(self.returnpointer));
        print "ALP memory: " + str(self.returnpointer.value)

    def projection(self):
        alp_cdll.AlpProjInquire(self.alp_id, ALP_PROJ_MODE, byref(self.returnpointer))
        print "ALP Projection Mode: " + str(self.returnpointer.value)

    def update_temperature(self):
        alp_cdll.AlpDevInquire(self.alp_id, ALP_DDC_FPGA_TEMPERATURE, byref(self.returnpointer))
        self.temps['DDC'] = self.returnpointer.value / 256

        alp_cdll.AlpDevInquire(self.alp_id, ALP_APPS_FPGA_TEMPERATURE, byref(self.returnpointer))
        self.temps['APPS'] = self.returnpointer.value / 256

        alp_cdll.AlpDevInquire(self.alp_id, ALP_PCB_TEMPERATURE, byref(self.returnpointer))
        self.temps['PCB'] = self.returnpointer.value / 256

    def upload_multiseq(self, ptn, timing, triggerMode=True, bitnum=1):
        """
        upload a series of frames, with one defined sequence per frame. This allows for varying frame durations.
        ptn: list of numpy arrays, each size (self.ImHeight, self.ImWidth)
        timing: duration (in milliseconds) of each frame in order
        triggerMode: frames are advanced by external trigger
        """

        start = time.clock()
        # insert empty frame with 0 duration at the beginning
        # ensures that the first frame is empty while waiting for trigger
        timing = np.insert(timing, 0, 0)
        blankframe = np.zeros_like(ptn[0])
        ptn.insert(0, blankframe)
        ctypes._reset_cache()

        for p, t in zip(ptn, timing):
            seq = self.seq_alloc(bitnum, 1)
            self.seq_timing(seq, t * 1000, 0)  # convert from ms to us
            self.seq_upload(seq, [p])

            if triggerMode:
                self.seq_start(seq)
            # print 'seq uploaded'
            self.seq_handles.append(seq)
        end = time.clock()
        print "Uploaded " + str(len(ptn)) + " in " + str(end - start) + "s"

    def upload_singleptn(self, ptn, dur, bitnum=1):
        # single pattern that loops. in slave mode, can be triggered every time TTL pulse received

        picnum = 1L
        stimon_time = dur * 1000L  # microseconds
        stimoff_time = 0L
        seq_id = self.seq_alloc(bitnum, picnum)

        self.seq_handles = []
        self.seq_handles.append(seq_id)

        print stimon_time, stimoff_time
        self.seq_timing(seq_id, stimon_time, stimoff_time)

        self.seq_upload(seq_id, [ptn])
        self.seq_start_loop(seq_id)

    def upload_singleseq(self, ptn, framedur=10, bitnum=1):
        # single sequence with fixed frame dur
        picnum = len(ptn)
        stimon_time = framedur * 1000L  # microseconds
        stimoff_time = 0L
        seq_id = self.seq_alloc(bitnum, picnum)

        self.seq_handles = []
        self.seq_handles.append(seq_id)

        print 'UPLOADING TO ALP...'
        print len(ptn)
        start = time.clock()
        self.seq_timing(seq_id, stimon_time, stimoff_time)
        self.seq_upload(seq_id, ptn)
        end = time.clock()

        print 'Sequence uploaded in ' + str(end - start) + ' ms'

    def Ptn2Char(self, ptn):
        # handle ALP patterns
        # flatten pattern sequence to a list, then put in ctype char vector
        ptn_list = []
        for frame in ptn:
            # flatten frame and add it to list
            ptn_list.extend(frame.flatten().tolist())

        alp_seqdata = c_ubyte * len(ptn_list)
        alp_seqdata = alp_seqdata()

        # now transfer elementwise from list to char vector (is there better way?)
        for i in range(len(alp_seqdata)):
            alp_seqdata[i] = int(ptn_list[i])
        return alp_seqdata

    def Ptn2Char_fast(self, ptn):
        c_ubyte_p = POINTER(c_ubyte)
        start = time.clock()

        nFrames = len(ptn)
        alp_seqdata = np.zeros([self.pixelsPerIm * nFrames])

        for i, frame in enumerate(ptn):
            start_ind = i * self.pixelsPerIm
            end_ind = (i + 1) * self.pixelsPerIm
            alp_seqdata[start_ind:end_ind] = frame.flatten()

        alp_seqdata = alp_seqdata.astype('int')
        arr = alp_seqdata.tolist()
        arr = (c_ubyte * len(arr)).from_buffer_copy(str(bytearray(arr)))
        return arr
        # alp_seqdata = alp_seqdata.ctypes.data_as(self.c_ubyte_p)
        end = time.clock()

        return alp_seqdata.ctypes.data_as(c_ubyte_p)

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
            returnvalue = alp_cdll.AlpProjControl(self.alp_id, ALP_PROJ_MODE, alpmode[mode])
            print 'set PROJ_MODE: ' + mode + ' ' + str(returnvalue)

            if mode == 'TTL_seqonset':
                # sequence init upon TTL
                self.set_trigger_edge('rising')

                print mode + str(returnvalue)

            if mode == 'single_TTL':
                # frames are advanced when TTL pulse is high, in sequence queue mode

                returnvalue = alp_cdll.AlpProjControl(self.alp_id, ALP_PROJ_STEP, ALP_LEVEL_HIGH)
                # step to next frame on rising TTL edge
                print 'single_TTL: ' + str(returnvalue)

                self.seq_queue_mode()

        else:
            self.stop()
            self.shutdown()
            print "Desired mode is: " + "'" + str(mode) + "'"
            print "Available modes are: "
            print alpmode.keys()
            raise ValueError('Cannot set projector mode, shutting down...')

    def seq_alloc(self, bitnum, picnum):
        """pre-allocate memory for sequence
        bitnum: bit-depth of sequence, e.g. '1L'
        picnum: # frames in sequence, e.g. '2L'
        
        returns pointer to this sequence. to free memory, use seq_free()
        """
        seq_id = c_long()  # pointer to seq id

        returnvalue = alp_cdll.AlpSeqAlloc(self.alp_id, bitnum, picnum, byref(seq_id))
        # print 'seq_alloc with value: ' + str(returnvalue)
        return seq_id

    def seq_free(self, seq_id):
        """free sequence (specify using handle) from memory """

        returnvalue = alp_cdll.AlpSeqFree(self.alp_id, seq_id)
        if returnvalue == 1003:
            raise ValueError('Try DMD.stop() before attempting to release sequence')
        print 'seq_free: ' + str(returnvalue)

    def seq_free_all(self):
        """clear all sequences from DMD"""
        for seq in self.seq_handles:
            self.seq_free(seq)

        self.seq_handles = []

    def seq_timing(self, seq_id, stimon_time, stimoff_time):
        """set sequence timing parameters (Master Mode)
        stimon_time e.g. 800000L (microseconds)
        stimoff_time e.g. 200000L
        """

        PictureTime = stimon_time + stimoff_time  # ALP-4.2: time between consecutive stim onsets

        returnvalue = alp_cdll.AlpSeqTiming(self.alp_id, seq_id, stimon_time, PictureTime, 0, ALP_DEFAULT, ALP_DEFAULT)
        # print 'seq_timing with value: ' + str(returnvalue)

    def seq_upload(self, seq_id, ptn):
        """
        uploads single sequence to DMD
        ptn: list of numpy arrays, each array is one frame in sequence, size [self.ImHeight, self.ImWidth]
        """

        picnum = len(ptn)
        PicOffset = 0
        start = time.clock()
        seq_data = self.Ptn2Char_fast(ptn)
        end = time.clock()
        # print str((end-start)) + 's for Ptn2Char'
        returnvalue = alp_cdll.AlpSeqPut(self.alp_id, seq_id, PicOffset, picnum, seq_data)
        del seq_data
        # print 'seq_upload with value: ' + str(returnvalue)

    def seq_start(self, seq_id):
        returnvalue = alp_cdll.AlpProjStart(self.alp_id, seq_id)
        # print 'seq_start: ' + str(returnvalue)

    def seq_start_loop(self, seq_id):
        returnvalue = alp_cdll.AlpProjStartCont(self.alp_id, seq_id)
        print 'seq_start (loops): ' + str(returnvalue)

    def seq_queue_mode(self):
        returnvalue = alp_cdll.AlpProjControl(self.alp_id, ALP_PROJ_QUEUE_MODE, ALP_PROJ_SEQUENCE_QUEUE)
        print 'Sequence queue set with : ' + str(returnvalue)

    def set_trigger_edge(self, edge_type):
        alp_edge_type = {'rising':
                             ALP_EDGE_RISING,
                         'falling':
                             ALP_EDGE_FALLING
                         }

        if edge_type in alp_edge_type:
            alp_trigger_value = alp_edge_type[edge_type]
            returnvalue = alp_cdll.AlpDevControl(self.alp_id, ALP_TRIGGER_EDGE, alp_trigger_value)
            print edge_type + ' trigger set with value: ' + str(returnvalue)

        else:
            self.stop()
            self.shutdown()
            print "Desired trigger is: " + "'" + str(edge_type) + "'"
            print "Available modes are: "
            print alp_edge_type.keys()
            raise ValueError('Cannot set trigger edge , shutting down...')

    def stop(self):
        returnvalue = alp_cdll.AlpDevHalt(self.alp_id)
        print 'seq_stop: ' + str(returnvalue)

    def shutdown(self):
        returnvalue = alp_cdll.AlpDevFree(self.alp_id)
        print 'Shutdown value: ' + str(returnvalue)

    def __del__(self):
        self.shutdown()


class AlpError(Exception):
    pass

class AlpOutOfMemoryError(AlpError):
    pass


try:
    alp_cdll = CDLL('alpV42.dll')
except WindowsError as e:
    raise AlpError("The directory containing 'alpV42.dll' is not found in the system (Windows) path. "
                   "Please add it to use this package.")
