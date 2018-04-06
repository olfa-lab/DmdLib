"""
Module handling the communication with OpenEphys.
"""
import zmq

TIMEOUT_MS = 250  # time to wait for ZMQ socket to respond before error.
HOSTNAME = 'localhost'
PORT = 5556

_ctx = zmq.Context()  # should be only one made per process.


class OpenEphysComms:

    def __init__(self, hostname=HOSTNAME, port=PORT):
        """
        :param hostname: where to connect to OpenEphys ZMQ socket (default: 'localhost')
        :param port: port to connect openephys socket (default: 5556)
        """
        self.hostname = hostname
        self.port = port

    def send_message(self, msg:str):
        """
        sends a message to openephys ZMQ socket.

        Raises OpenEphysError if port is unresponsive.

        :param msg: string
        :param hostname: ip address to send to
        :param port: zmq port number
        :return: none
        """

        failed = False
        with _ctx.socket(zmq.REQ) as sock:
            sock.connect('tcp://{}:{}'.format(self.hostname, self.port))
            sock.send_string(msg, zmq.NOBLOCK)
            evs = sock.poll(TIMEOUT_MS)  # wait for host process to respond.

            # Poll returns 0 after timeout if no events detected. This means that openephys is broken, so error:
            if evs < 1:
                failed = True
            else:
                sock.recv_string()
        if failed:  # raise out of context (after socket is closed...)
            raise OpenEphysError('Cannot connect to OpenEphys.')

    def record_start(self, uuid:str, filepath:str):
        """
        Convenience function for sending data about the start of a recording to OpenEphys
        :param uuid: UUID string to send to recording device
        :param filepath: Filepath string to send to recording device
        :return:
        """
        msg = 'Pattern file saved at: {}.'.format(filepath)
        self.send_message(msg)
        msg2 = 'Pattern file uuid: {}.'.format(uuid)
        self.send_message(msg2)


    def record_presentation(self, group_name:str):
        """
        Convenience function for sending data about start of a presentation epoch.
    
        :param group_name: name of the epoch (ie AAA, AAB, etc).
        """
        msg = 'Starting presentation {}'.format(group_name)
        self.send_message(msg)


class OpenEphysError(Exception):
    pass
