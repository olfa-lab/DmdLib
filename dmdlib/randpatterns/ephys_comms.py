"""
Module handling the communication with OpenEphys.
"""
import zmq

TIMEOUT_MS = 250  # time to wait for ZMQ socket to respond before error.
HOSTNAME = 'localhost'
PORT = 5556

_ctx = zmq.Context()  # should be only one made per process.


def send_message(msg, hostname=HOSTNAME, port=PORT):
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
        sock.connect('tcp://{}:{}'.format(hostname, port))
        sock.send_string(msg, zmq.NOBLOCK)
        evs = sock.poll(TIMEOUT_MS)  # wait for host process to respond.

        # Poll returns 0 after timeout if no events detected. This means that openephys is broken, so error:
        if evs < 1:
            failed = True
        else:
            sock.recv_string()
    if failed:  # raise out of context (after socket is closed...)
        raise OpenEphysError('Cannot connect to OpenEphys.')

def record_start(uuid, filepath, hostname=HOSTNAME, port=PORT):
    """
    Convenience function for sending data about the start of a recording to OpenEphys
    :param uuid:
    :param filepath:
    :param hostname:
    :param port:
    :return:
    """
    msg = 'Pattern file saved at: {}.'.format(filepath)
    send_message(msg, hostname, port)
    msg2 = 'Pattern file uuid: {}.'.format(uuid)
    send_message(msg2, hostname, port)


def record_presentation(name, hostname=HOSTNAME, port=PORT):
    """
    Convenience function for sending data about start of a presentation epoch.

    :param name: name of the epoch (ie AAA, AAB, etc).
    :param hostname: default 'localhost'
    :param port: default 5556
    """
    msg = 'Starting presentation {}'.format(name)
    send_message(msg, hostname, port)


class OpenEphysError(Exception):
    pass
