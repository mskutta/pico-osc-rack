#from usocket import socket
from machine import Pin, SPI, I2C
from ssd1306 import SSD1306_I2C
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

def init_display():
    # Initialize I2C with GPIO 4 (SDA) and GPIO 5 (SCL)
    i2c = I2C(1, sda=Pin(26), scl=Pin(27), freq=400000)
    time.sleep(1)
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
    y = 16 + (row * 12)  # First row starts at 16, 12 pixels per row
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
    
    w5x00_init()
    client = OSCClient(config.config['osc_ip'], config.config['osc_port'])

    # Initialize pins from config
    pins = [Pin(i, Pin.IN, Pin.PULL_UP) for i in config.config['pins']]
    previous_states = [pin.value() for pin in pins]
    trigger_counts = [0] * len(pins)  # Track number of triggers for each pin
    
    while True:
        try:
            if not client.connected:
                client.connect()
                display.fill(0)  # Clear display
                display.text("Connected!", 0, 0)
                display.show()
                print("Connected to OSC server")

            display.fill(0)  # Clear display
            display.text("Running...", 0, 0)  # Status line

            for i, pin in enumerate(pins):
                current_state = pin.value()
                if current_state != previous_states[i]:
                    try:
                        if current_state == 0:  # Pin triggered
                            trigger_counts[i] += 1
                            print(f"Pin {i+1} triggered")
                            client.send_message(config.config['addresses'][i])
                        else:
                            print(f"Pin {i+1} untriggered")
                        previous_states[i] = current_state
                    except OSError as e:
                        print(f"Socket error while sending: {e}")
                        client.close()
                        time.sleep(1)
                        continue

                # Draw grid cell
                col = i % 2  # 2 columns
                row = i // 2  # 4 rows
                cell_text = f"P{i+1}:{trigger_counts[i]}"
                draw_grid_cell(display, col, row, cell_text, current_state == 0)

            display.show()

            led.value(1)
            time.sleep(0.1)
            led.value(0)
            time.sleep(0.1)

        except OSError as e:
            print(f"Connection error: {e}")
            client.close()
            time.sleep(1)

if __name__ == "__main__":
    main()