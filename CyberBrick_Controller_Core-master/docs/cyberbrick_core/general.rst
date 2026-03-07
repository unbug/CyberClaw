.. _esp32_general:

General information about the ESP32 port
========================================

The ESP32-C3 is a popular WiFi and Bluetooth enabled System-on-Chip (SoC) by
Espressif Systems.

Multitude of boards
-------------------

There is a multitude of modules and boards from different sources which carry
the ESP32-C3 chip. MicroPython tries to provide a generic port which would run on
as many boards/modules as possible, but there may be limitations. Espressif
development boards are taken as reference for the port (for example, testing is
performed on them).  For any board you are using please make sure you have a
datasheet, schematics and other reference materials so you can look up any
board-specific functions.

To make a generic ESP32-C3 port and support as many boards as possible the
following design and implementation decision were made:

* GPIO pin numbering is based on ESP32-C3 chip numbering.  Please have the manual/pin
  diagram of your board at hand to find correspondence between your board pins and
  actual ESP32-C3 pins.
* All pins are supported by MicroPython but not all are usable on any given board.
  For example pins that are connected to external SPI flash should not be used,
  and a board may only expose a certain selection of pins.


Technical specifications and SoC datasheets
-------------------------------------------

The datasheets and other reference material for ESP32 chip are available
from the vendor site: https://www.espressif.com/en/support/download/documents?keys=esp32-c3 .
They are the primary reference for the chip technical specifications, capabilities,
operating modes, internal functioning, etc.

For your convenience, some of technical specifications are provided below:

* Architecture: RISC-V 32-bit
* CPU frequency: up to 160MHz
* Total RAM available: 400KB (part of it reserved for system)
* BootROM: 384KB
* Internal FlashROM: none
* External FlashROM: code and data, via SPI Flash; usual size 4MB
* GPIO: 22 (GPIOs are multiplexed with other functions, including
  external FlashROM, UART, etc.)
* UART: 2 RX/TX UART
* SPI: 3 SPI interfaces (one used for FlashROM)
* I2C: 1 I2C (bitbang implementation available on any pins)
* ADC: 12-bit SAR ADC up to 6 channels
* RMT: 6 channels allowing accurate pulse transmit/receive

For more information see the ESP32 datasheet: https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf

MicroPython is implemented on top of the ESP-IDF, Espressif's development
framework for the ESP32.  This is a FreeRTOS based system.  See the
`ESP-IDF Programming Guide <https://docs.espressif.com/projects/esp-idf/en/latest/index.html>`_
for details.
