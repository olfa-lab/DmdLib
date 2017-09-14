import zmq


def send_message(msg, hostname='localhost', port=5556):
    with zmq.Context() as ctx:
        with ctx.socket(zmq.REQ) as sock:
            sock.connect('tcp://{}:{}'.format(hostname, port))
            sock.send_string(msg)
            _ = sock.recv_string()
    return

