import zmq


def send_message(msg, hostname='localhost', port=5556):
    """
    sends a message to openephys ZMQ socket.
    :param msg: string
    :param hostname: ip address to send to
    :param port: zmq port number
    :return: none
    """
    with zmq.Context() as ctx:
        with ctx.socket(zmq.REQ) as sock:
            sock.connect('tcp://{}:{}'.format(hostname, port))
            sock.send_string(msg)
            _ = sock.recv_string()
    return

