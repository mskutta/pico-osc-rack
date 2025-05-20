#from usocket import socket
from machine import Pin, SPI, I2C, SoftI2C
from ssd1306 import SSD1306_I2C
import network
import time
from config import Config
from oscclientudp import OSCClient
# import mdns_client

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

def init_display():
    # Initialize I2C with GPIO 26 (SDA) and GPIO 27 (SCL)
    # i2c = I2C(1, sda=Pin(26), scl=Pin(27))
    i2c = SoftI2C(scl=Pin(27), sda=Pin(26))
    time.sleep(2)
    devices = i2c.scan()
    if not devices:
        print("No I2C devices found!")

    if devices:
        for device in devices:
            print(f"I2C device found at address: {hex(device)}")
    display = SSD1306_I2C(128, 64, i2c)  # 128x64 is the common resolution
    return display

def draw_grid_cell(display, col, row, text, inverted=False):
    x = col * 64  # 128/2 = 64 pixels per column
    y = 15 + (row * 12)  # First row starts at 16, 12 pixels per row
    if inverted:
        # Draw filled rectangle
        display.fill_rect(x, y, 64, 12, 1)
        # Draw text in inverse
        display.text(text, x + 2, y + 2, 0)
    else:
        # Draw text normally
        display.text(text, x + 2, y + 2, 1)

def main():
    config = Config()
    display = init_display()
    display.text("Initializing...", 0, 0)
    display.show()

    # # Detect qLab via mDNS, if more than one, use the first
    # try:
    #     mdns.start()
    #     time.sleep(1)  # Give mDNS time to discover
    #     services = mdns.browse('_qlab._tcp')
    #     if services:
    #         qlab = services[0]  # Take first qLab instance
    #         config.config['osc_ip'] = qlab['ip']
    #         config.config['osc_port'] = qlab['port']
    #         print(f"Found qLab at {qlab['ip']}:{qlab['port']}")
    #     else:
    #         print("No qLab instances found")
    # except ImportError:
    #     print("mDNS not supported")
    # except Exception as e:
    #     print(f"mDNS error: {e}")

    
    w5x00_init()
    client = OSCClient(config.config['osc_ip'], config.config['osc_port'])

    # Initialize pins 2-9 as inputs with pull-up resistors
    pins = [Pin(i, Pin.IN, Pin.PULL_UP) for i in list(range(2, 10))]
    previous_states = [pin.value() for pin in pins]
    trigger_counts = [0] * len(pins)  # Track number of triggers for each pin
    
    last_run = time.ticks_ms()
    run_interval = 100  # 100ms interval

    while True:
        try:
            # Check if it's time to run the main loop
            # This is a simple way to throttle the loop
            # to avoid overwhelming the display and network
            # and to ensure we don't send too many OSC messages
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_run) >= run_interval:
                last_run = current_time

                display.fill(0)  # Clear display
                display.text("Running...", 0, 0)  # Status line
            
                for i, pin in enumerate(pins):
                    current_state = pin.value()
                    if current_state != previous_states[i]:
                        if current_state == 0:  # Pin triggered
                            trigger_counts[i] += 1
                            print(f"Pin {i+1} triggered")
                        else:
                            print(f"Pin {i+1} untriggered")
                        previous_states[i] = current_state

                    if current_state == 0:  # Pin triggered
                        try:
                            client.send_message(config.config['addresses'][i])
                        except OSError as e:
                            print(f"OSC Error: {e}")

                    # loop over the run states and draw the grid
                    col = i % 2
                    row = i // 2
                    cell_text = f"P{i+1}:{trigger_counts[i]}"
                    draw_grid_cell(display, col, row, cell_text, current_state == 0)

                try:
                    display.show()
                except OSError as e:
                    print(f"Display Error: {e}")

                led.toggle()

        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(1)  # Delay before retrying

if __name__ == "__main__":
    main()