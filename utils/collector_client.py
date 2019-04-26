# -*- coding: utf-8 -*-
import socket

__all__ = ['send_event']


def send_event(event, settings):
    output_settings = settings['output']
    ip = output_settings['ip']
    port = output_settings['port']

    if not event:
        return

    message = bytes('{}\n'.format(event), 'utf-8')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((ip, port))
        sock.sendall(message)
    except socket.error:
        print("ERROR: Cannot send event, server unavailable")
        print("Event data: {}".format(message))
    finally:
        sock.close()
