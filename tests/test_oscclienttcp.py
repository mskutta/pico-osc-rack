import ast
from pathlib import Path
import select
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from oscclienttcp import OSCClient


class FakeSocket:
    def __init__(self):
        self.data = bytearray()
        self.replies = []
        self.writes = []
        self.flags = 0
        self.closed = False
        self.connect_error = False

    def settimeout(self, value):
        pass

    def connect(self, address):
        if self.connect_error:
            raise OSError('connection refused')

    def send(self, data):
        action = self.writes.pop(0) if self.writes else len(data)
        if isinstance(action, Exception):
            raise action
        self.data.extend(data[:action])
        return action

    def recv(self, size):
        return self.replies.pop(0)

    def close(self):
        self.closed = True


class FakePoll:
    def register(self, sock, flags):
        self.sock = sock

    def poll(self, timeout):
        assert timeout == 0
        flags = self.sock.flags
        if self.sock.replies:
            flags |= select.POLLIN
        return [(self.sock, flags)] if flags else []


class TCPTests(unittest.TestCase):
    def setUp(self):
        self.sockets = []
        self.patchers = [
            patch('oscclienttcp.socket.socket', self.new_socket),
            patch('oscclienttcp.select.poll', FakePoll),
            patch('builtins.print'),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = OSCClient('test', 53000)

    def new_socket(self, *args):
        sock = FakeSocket()
        self.sockets.append(sock)
        return sock

    def test_slip_framing_and_partial_writes(self):
        self.client.connect()
        self.sockets[0].writes = [2, 3]
        self.client.send_message('/cue/1/go')
        self.assertEqual(self.sockets[0].data,
                         b'\xc0/cue/1/go\x00\x00\x00,\x00\x00\x00\xc0')
        self.assertEqual(self.client._slip_encode(b'\xc0\xdb'),
                         b'\xc0\xdb\xdc\xdb\xdd\xc0')

    def test_eof_reconnects_before_next_send(self):
        self.client.connect()
        self.sockets[0].replies = [b'']
        self.client.send_message('/cue/1/go')
        self.assertTrue(self.sockets[0].closed)
        self.assertEqual(len(self.sockets), 2)
        self.assertTrue(self.sockets[1].data)
        self.assertFalse(self.sockets[0].data)

    def test_hangup_and_error_close_connection(self):
        for flag in (select.POLLHUP, select.POLLERR):
            self.client.connect()
            self.sockets[-1].flags = flag
            self.client.service()
            self.assertFalse(self.client.connected)
            self.assertTrue(self.sockets[-1].closed)

    def test_replies_drained_with_bounded_work(self):
        self.client.connect()
        self.sockets[0].replies = [b'reply'] * 10
        self.client.service()
        self.assertEqual(len(self.sockets[0].replies), 6)
        self.client.service()
        self.client.service()
        self.assertEqual(self.sockets[0].replies, [])
        self.assertTrue(self.client.connected)

    def test_send_failure_before_any_bytes_retries_once(self):
        self.client.connect()
        self.sockets[0].writes = [OSError('reset')]
        self.client.send_message('/cue/1/go')
        self.assertEqual(len(self.sockets), 2)
        self.assertTrue(self.sockets[0].closed)
        self.assertTrue(self.sockets[1].data)

    def test_partial_send_failure_is_not_replayed(self):
        self.client.connect()
        self.sockets[0].writes = [3, OSError('reset')]
        with self.assertRaises(OSError):
            self.client.send_message('/cue/1/go')
        self.assertEqual(len(self.sockets), 1)
        self.assertFalse(self.client.connected)

    def test_retry_failure_stops_and_later_trip_recovers(self):
        def broken_socket(*args):
            sock = self.new_socket()
            sock.writes = [OSError('reset')]
            return sock
        with patch('oscclienttcp.socket.socket', broken_socket):
            with self.assertRaises(OSError):
                self.client.send_message('/cue/1/go')
        self.assertEqual(len(self.sockets), 2)
        self.assertTrue(all(sock.closed for sock in self.sockets))
        self.client.send_message('/cue/2/go')
        self.assertTrue(self.client.connected)

    def test_failed_connect_closes_socket(self):
        def refused_socket(*args):
            sock = self.new_socket()
            sock.connect_error = True
            return sock
        with patch('oscclienttcp.socket.socket', refused_socket):
            with self.assertRaises(OSError):
                self.client.send_message('/cue/1/go')
        self.assertTrue(self.sockets[0].closed)
        self.assertFalse(self.client.connected)

    def test_long_run_with_replies_and_disconnects(self):
        for i in range(1000):
            if self.client.connected:
                self.sockets[-1].replies.append(b'' if i % 25 == 0 else b'reply')
            self.client.send_message('/cue/1/go')
        expected = self.client._slip_encode(self.client._format_message('/cue/1/go'))
        data = b''.join(bytes(sock.data) for sock in self.sockets)
        self.assertEqual(data, expected * 1000)
        self.assertGreater(len(self.sockets), 1)


class SensorTests(unittest.TestCase):
    def test_holding_and_clearing_sensor_with_send_errors(self):
        # Run the actual main() with simulated hardware and timed samples.
        node = next(n for n in ast.parse(Path('main.py').read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'main')
        high = [1] * 8
        low = [0] + [1] * 7
        frames = [high, low, low, low, high, low, low]
        state = {'frame': 0, 'ticks': 0}
        sent = []

        class StopTest(BaseException):
            pass

        class Pin:
            IN = PULL_UP = 0

            def __init__(self, number, *args):
                self.index = number - 2

            def value(self):
                return frames[state['frame']][self.index]

        class Client:
            def __init__(self, *args):
                pass

            def service(self):
                pass

            def send_message(self, address):
                sent.append(address)
                raise OSError('simulated network failure')

        class Display:
            def __getattr__(self, name):
                return lambda *args: None

        def ticks():
            if state['ticks'] == len(frames):
                raise StopTest()
            state['frame'] = state['ticks']
            state['ticks'] += 1
            return state['frame'] * 100

        env = dict(
            Config=lambda: SimpleNamespace(config={
                'osc_ip': 'test', 'osc_port': 53000, 'addresses': list(range(8))}),
            init_display=Display, w5x00_init=lambda: None, OSCClient=Client, Pin=Pin,
            time=SimpleNamespace(ticks_ms=ticks, ticks_diff=lambda a, b: a-b,
                                 sleep=lambda n: None),
            draw_grid_cell=lambda *args: None,
            led=SimpleNamespace(toggle=lambda: None), print=lambda *args: None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'main.py', 'exec'), env)
        with self.assertRaises(StopTest):
            env['main']()
        self.assertEqual(sent, [0, 0])


if __name__ == '__main__':
    unittest.main()
