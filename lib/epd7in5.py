# Vendored from https://github.com/waveshare/Pico_ePaper_Code/blob/main/python/Pico-ePaper-7.5.py
# Waveshare 7.5" 800x480 B&W e-paper driver for Raspberry Pi Pico (MicroPython)
# Demo/main block removed; class preserved as-is.

from machine import Pin, SPI
import framebuf
import utime

EPD_WIDTH = 800
EPD_HEIGHT = 480

RST_PIN = 12
DC_PIN = 8
CS_PIN = 9
BUSY_PIN = 13


class EPD_7in5:
    def __init__(self):
        self.reset_pin = Pin(RST_PIN, Pin.OUT)
        self.busy_pin = Pin(BUSY_PIN, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(CS_PIN, Pin.OUT)
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

        self.spi = SPI(1)
        self.spi.init(baudrate=20_000_000)
        self.dc_pin = Pin(DC_PIN, Pin.OUT)

        self.init()

    def digital_write(self, pin, value):
        pin.value(value)

    def digital_read(self, pin):
        return pin.value()

    def delay_ms(self, delaytime):
        utime.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

    def module_exit(self):
        self.digital_write(self.reset_pin, 0)

    def reset(self):
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)

    def send_command(self, command):
        self.digital_write(self.dc_pin, 0)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([command])
        self.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([data])
        self.digital_write(self.cs_pin, 1)

    def send_data1(self, buf):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf) if not isinstance(buf, (bytes, bytearray)) else buf)
        self.digital_write(self.cs_pin, 1)

    def _bulk_data_write(self, buf):
        """Write a bytes/bytearray buffer to SPI with DC=1 (no copy)."""
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(buf)
        self.digital_write(self.cs_pin, 1)

    def WaitUntilIdle(self):
        while self.digital_read(self.busy_pin) == 0:
            self.send_command(0x71)
            self.delay_ms(20)

    def TurnOnDisplay(self):
        self.send_command(0x12)
        self.delay_ms(100)
        self.WaitUntilIdle()

    def init(self):
        self.reset()

        self.send_command(0x06)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x28)
        self.send_data(0x17)

        self.send_command(0x01)
        self.send_data(0x07)
        self.send_data(0x07)
        self.send_data(0x28)
        self.send_data(0x17)

        self.send_command(0x04)
        self.delay_ms(100)
        self.WaitUntilIdle()

        self.send_command(0X00)
        self.send_data(0x1F)

        self.send_command(0x61)
        self.send_data(0x03)
        self.send_data(0x20)
        self.send_data(0x01)
        self.send_data(0xE0)

        self.send_command(0X15)
        self.send_data(0x00)

        self.send_command(0X50)
        self.send_data(0x10)
        self.send_data(0x07)

        self.send_command(0X60)
        self.send_data(0x22)

        return 0

    def init_fast(self):
        self.reset()

        self.send_command(0X00)
        self.send_data(0x1F)

        self.send_command(0X50)
        self.send_data(0x10)
        self.send_data(0x07)

        self.send_command(0x04)
        self.delay_ms(100)
        self.WaitUntilIdle()

        self.send_command(0x06)
        self.send_data(0x27)
        self.send_data(0x27)
        self.send_data(0x18)
        self.send_data(0x17)

        self.send_command(0xE0)
        self.send_data(0x02)
        self.send_command(0xE5)
        self.send_data(0x5A)

        return 0

    def init_part(self):
        self.reset()

        self.send_command(0X00)
        self.send_data(0x1F)

        self.send_command(0x04)
        self.delay_ms(100)
        self.WaitUntilIdle()

        self.send_command(0xE0)
        self.send_data(0x02)
        self.send_command(0xE5)
        self.send_data(0x6E)

        return 0

    def Clear(self):
        high = self.height
        wide = self.width // 8 if self.width % 8 == 0 else self.width // 8 + 1

        self.send_command(0x10)
        for i in range(0, wide):
            self.send_data1([0xff] * high)

        self.send_command(0x13)
        for i in range(0, wide):
            self.send_data1([0x00] * high)

        self.TurnOnDisplay()

    def ClearBlack(self):
        high = self.height
        wide = self.width // 8 if self.width % 8 == 0 else self.width // 8 + 1

        self.send_command(0x10)
        for i in range(0, wide):
            self.send_data1([0x00] * high)

        self.send_command(0x13)
        for i in range(0, wide):
            self.send_data1([0xff] * high)

        self.TurnOnDisplay()

    def display(self, Image):
        wide = self.width // 8 if self.width % 8 == 0 else self.width // 8 + 1
        high = self.height

        # First frame buffer: send image as-is in one bulk write.
        self.send_command(0x10)
        self._bulk_data_write(Image)

        # Second frame buffer: send bitwise-inverted image row by row.
        # Row-by-row avoids allocating a second 48 KB buffer while reducing
        # Python-level calls from 48,000 (one per byte) to 480 (one per row).
        self.send_command(0x13)
        row = bytearray(wide)
        for j in range(high):
            base = j * wide
            for i in range(wide):
                row[i] = ~Image[base + i] & 0xFF
            self._bulk_data_write(row)

        self.TurnOnDisplay()

    def display_Partial(self, Image, Xstart, Ystart, Xend, Yend):
        if ((Xstart % 8 + Xend % 8 == 8 & Xstart % 8 > Xend % 8) | Xstart % 8 + Xend % 8 == 0 | (Xend - Xstart) % 8 == 0):
            Xstart = Xstart // 8 * 8
            Xend = Xend // 8 * 8
        else:
            Xstart = Xstart // 8 * 8
            Xend = Xend // 8 * 8 if Xend % 8 == 0 else Xend // 8 * 8 + 1

        Width = (Xend - Xstart) // 8
        Height = Yend - Ystart

        self.send_command(0x50)
        self.send_data(0xA9)
        self.send_data(0x07)

        self.send_command(0x91)
        self.send_command(0x90)
        self.send_data(Xstart // 256)
        self.send_data(Xstart % 256)
        self.send_data((Xend - 1) // 256)
        self.send_data((Xend - 1) % 256)
        self.send_data(Ystart // 256)
        self.send_data(Ystart % 256)
        self.send_data((Yend - 1) // 256)
        self.send_data((Yend - 1) % 256)
        self.send_data(0x01)

        self.send_command(0x13)
        for j in range(Height):
            for i in range(Width):
                self.send_data(~Image[i + j * Width])

        self.send_command(0x12)
        self.delay_ms(100)
        self.WaitUntilIdle()

    def sleep(self):
        self.send_command(0x50)
        self.send_data(0XF7)
        self.send_command(0x02)
        self.WaitUntilIdle()
        self.send_command(0x07)
        self.send_data(0xa5)
