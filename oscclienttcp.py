import socket
import struct

class OSCClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
    
    def connect(self):
        try:
            if self.socket:
                self.close()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5 second timeout
            self.socket.connect((self.host, self.port))
            self.connected = True
        except OSError as e:
            print(f"Connection failed: {e}")
            self.close()
            raise
        
    def close(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.connected = False
    
    def send_message(self, address, *args):
        """Send an OSC message with the given address and arguments"""
        if not self.connected:
            self.connect()
        
        try:
            # Format the OSC message
            msg = self._format_message(address, *args)
            print(f"Sending message: {msg}")
            
            # SLIP encode the message
            # SLIP encoding is used for OSC over TCP
            slip_packet = self._slip_encode(msg)
            self.socket.send(slip_packet)
        except OSError as e:
            self.close()
            raise
    
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