import socket
import struct
import select

class OSCClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.poller = None
    
    def connect(self):
        try:
            if self.socket:
                self.close()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5 second timeout
            self.socket.connect((self.host, self.port))
            self.poller = select.poll()
            self.poller.register(self.socket, select.POLLIN)
            self.connected = True
            print("OSC TCP connected")
        except OSError as e:
            print(f"Connection failed: {e}")
            self.close()
            raise
        
    def close(self):
        self.poller = None
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.connected = False

    def service(self):
        """Drain replies and detect a closed connection without waiting.

        Limit reads per call so incoming traffic cannot monopolize the
        sensor loop. QLab normally sends no reply for a successful /go,
        but can send errors or replies when /alwaysReply is enabled.
        """
        if not self.connected:
            return
        try:
            for _ in range(4):
                events = self.poller.poll(0)
                if not events:
                    return
                flags = events[0][1]
                if flags & (select.POLLERR | select.POLLHUP):
                    print("OSC TCP connection closed; reconnecting on next trip")
                    self.close()
                    return
                if not flags & select.POLLIN:
                    return
                reply = self.socket.recv(512)
                if not reply:
                    print("OSC TCP connection closed; reconnecting on next trip")
                    self.close()
                    return
                print("QLab reply: {}".format(reply))
        except OSError as e:
            print("OSC TCP receive error: {}".format(e))
            self.close()

    def send_message(self, address, *args):
        """Send an OSC message with the given address and arguments"""
        slip_packet = self._slip_encode(self._format_message(address, *args))
        self.service()
        for attempt in range(2):
            if not self.connected:
                self.connect()
            sent = 0
            try:
                # TCP writes can be partial; send the entire framed message.
                while sent < len(slip_packet):
                    count = self.socket.send(slip_packet[sent:])
                    if not count:
                        raise OSError("TCP connection closed during send")
                    sent += count
                print("OSC TCP sent: {}".format(address))
                return
            except OSError:
                self.close()
                # Retry once only if no bytes were accepted. Replaying after
                # a partial write could execute the same cue twice.
                if sent or attempt:
                    raise
                print("OSC TCP send failed before any bytes; reconnecting")
    
    def _pad_string(self, s):
        """Pad a string to be 4-byte aligned"""
        b = s.encode('utf-8') + b'\x00'
        return self._pad_bytes(b)
    
    def _pad_bytes(self, b):
        """Pad bytes to be 4-byte aligned"""
        padding = 0 if len(b) % 4 == 0 else 4 - (len(b) % 4)
        return b + b'\x00' * padding

    def _format_message(self, address, *args):
        """Format an OSC message with address and arguments"""
        if not address.startswith('/'):
            raise ValueError("OSC address pattern must start with /")

        # OSC address pattern
        address_padded = self._pad_string(address)
        
        # OSC type tag string - always starts with comma even for no args
        type_tag = ","
        binary_args = b''

        # Only process args if we have any
        if args:
            # First pass - build type tag string
            for arg in args:
                if isinstance(arg, int):
                    type_tag += "i"
                elif isinstance(arg, float):
                    type_tag += "f"
                elif isinstance(arg, str):
                    type_tag += "s"
                elif isinstance(arg, bytes):
                    type_tag += "b"
                else:
                    raise ValueError(f"Unsupported argument type: {type(arg)}")
        
            # Second pass - format the arguments
            for arg in args:
                if isinstance(arg, int):
                    binary_args += struct.pack(">i", arg)
                elif isinstance(arg, float):
                    binary_args += struct.pack(">f", arg)
                elif isinstance(arg, str):
                    binary_args += self._pad_string(arg)
                elif isinstance(arg, bytes):
                    size = struct.pack(">i", len(arg))
                    padded = self._pad_bytes(arg)
                    binary_args += size + padded

        type_tag_padded = self._pad_string(type_tag)
        
        # Combine all parts
        return address_padded + type_tag_padded + binary_args
    
    def _slip_encode(self, data):
        END = b'\xC0'
        ESC = b'\xDB'
        ESC_END = b'\xDC'
        ESC_ESC = b'\xDD'

        encoded = bytearray()
        encoded += END  # Optional: Start-of-packet marker

        for byte in data:
            if byte == 0xC0:
                encoded += ESC + ESC_END
            elif byte == 0xDB:
                encoded += ESC + ESC_ESC
            else:
                encoded.append(byte)

        encoded += END  # End-of-packet marker
        return encoded
