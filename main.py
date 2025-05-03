#from usocket import socket
from machine import Pin,SPI
import network
import time
from config import Config
from oscclient import OSCClient

led = Pin(25, Pin.OUT)

#W5x00 chip init
def w5x00_init():
    spi=SPI(0,2_000_000, mosi=Pin(19),miso=Pin(16),sck=Pin(18))
    nic = network.WIZNET5K(spi,Pin(17),Pin(20)) #spi,cs,reset pin
    nic.active(True)
    # The only difference from the example linked above, using 
    # 'dhcp' instead of manually specifying the network info
    nic.ifconfig('dhcp')
    while not nic.isconnected():
        time.sleep(1)
        print(nic.regs())
    print(nic.ifconfig())
        
def main():
    config = Config()
    w5x00_init()
    client = OSCClient(config.config['osc_ip'], config.config['osc_port'])

    # Initialize pins from config
    pins = [Pin(i, Pin.IN, Pin.PULL_UP) for i in config.config['pins']]
    previous_states = [pin.value() for pin in pins]
    
    while True:
        try:
            if not client.connected:
                client.connect()
                print("Connected to OSC server")

            for i, pin in enumerate(pins):
                current_state = pin.value()
                if current_state != previous_states[i]:
                    try:
                        if current_state == 0:
                            print(f"Pin {i+1} triggered")
                            client.send_message(config.config['addresses'][i])
                        else:
                            print(f"Pin {i+1} untriggered")
                        previous_states[i] = current_state
                    except OSError as e:
                        print(f"Socket error while sending: {e}")
                        client.close()
                        time.sleep(1)  # Wait before reconnecting
                        continue

            led.value(1)
            time.sleep(0.1)
            led.value(0)
            time.sleep(0.1)

        except OSError as e:
            print(f"Connection error: {e}")
            client.close()
            time.sleep(1)  # Wait before reconnecting

if __name__ == "__main__":
    main()