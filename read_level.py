from machine import Pin
from micropython import const
import time
import pyb
#import pulseio             # uncomment for CircuitPython

ONE_MICROSECOND = const(1.0e-6)
ONE_MILLISECOND = const(1.0e-3)
NUM_RESPONSE_BYTES = const(12)     # SeeLevel sensor returns 12 bytes when probed

# define GPIO pins used on Pico
SeeLevelSelectGPIO = 0
SeeLevelResponseGPIO = 1

# error counts
checksum_errs = 0
preamble_errs = 0
sensor_errs   = 0

# create GPIO Pin objects for comms with SeeLevel sensor
SeeLevelSelectPin = Pin(SeeLevelSelectGPIO, Pin.OUT)
SeeLevelResponsePin = Pin(SeeLevelResponseGPIO, Pin.IN)

# calibration data for each tank
SensorCal = { 0:[], 1:[], 2:[] }

# de-select all SeeLevel sensors
SeeLevelSelectPin.off()

def powerUpSensors():
    # raise power on the SeeLevel bus
    SeeLevelSelectPin.on()
    time.sleep(2.450*ONE_MILLISECOND)      # wait until sensors power up

def powerDownSensors():
    # lower power on the SeeLevel bus
    time.sleep(100*ONE_MILLISECOND)
    SeeLevelSelectPin.off()

def selectSeeLevel(sensorNum):
    # pulse the bus "n" times to address sensor #n (n=0, 1, 2, ...)
    for i in range(sensorNum+1):
        SeeLevelSelectPin.on()
        time.sleep(85*ONE_MICROSECOND)
        SeeLevelSelectPin.off()
        time.sleep(215*ONE_MICROSECOND)

    return

# my version of the pulseio.PulseIn method from CircuitPython
def PulsesIn(num_pulses):
    pulse_widths = []
    value_method = SeeLevelResponsePin.value    # cache to improve timing accuracy
    for i in range(num_pulses):
        while value_method(): pass
        start = pyb.micros()
        while not value_method(): pass
        width = pyb.elapsed_micros(start)
        pulse_widths.append(width)
    return pulse_widths

def readSeeLevelBytes():
    num_pulses = 8*NUM_RESPONSE_BYTES
    # first, collect all of the pulses in the sensor response
    # (use following if you are running with CircuitPython)
    #pulses = pulseio.PulseIn(SeeLevelResponsePin, num_pulses, True)
    #time.sleep(23*ONE_MILLISECOND)
    #while (len(pulses) != num_pulses): pass
    pulses = PulsesIn(8*NUM_RESPONSE_BYTES)

    byte_data = []
    # convert pulse widths into data bytes
    for byte_index in range(NUM_RESPONSE_BYTES,8):
        cur_byte_pulses = pulses[i*8:i*8+8]   # select pulses for next byte
        # bits were sent Big-Endian, so reverse them to simplify following bit-shifts
        cur_byte_pulses.reverse()
        # any pulse less than 26 microseconds is a logical "1", and "0" if greater
        sl_byte = sum([int(pw < 26) << i for i, pw in enumerate(cur_byte_pulses)])
        byte_data.append(sl_byte)
    #pulses.clear()     # uncomment for CircuitPython
    return bytes(byte_data)

# decodeTankLevel returns percentage of tank filled
def decodeTankLevel(sensorData, calibrationData):
    print("sensor data: " + sensorData)
    tankLevel = 0

    # determine number of segments used by sensor
    base_seg = len(sensorData)-1
    # sensor returns zero for unavailable segments
    while base_seg > 0 :
        if sensorData[base_seg] == 0:
            base_seg -= 1
        else:
            break;

    # get first non-empty segment
    level_seg = 0
    while level_seg < len(sensorData) :
        if sensorData[level_seg] == 0:
            level_seg += 1
        else:
            break;
    if level_seg == len(sensordata):
        return 0    # all segments are zero, so tank is empty

    if calibrationData == []:
        # calibration data is not available, so guestimate tank level
        # assuming tank is a rectangular solid.
        # compute differential percentage of tank represented by each segment
        avg_contribution_per_segment = 100.0/(base_seg+1)
        # in case segment maximums dont max out (ie, reach 255),
        # average the filled segments to better estimate contribution 
        # from the segment spanning current water level.
        avg_reading_per_seg = sum(sensorData[level_seg+1:])/(base_seg+1)
        tankLevel = (sensorData[level_seg]/avg_reading_per_seg + (base_seg-level_seg))*avg_contribution_per_segment
        if tankLevel > 100: tankLevel = 100
    else:
        tankLevel = -1      # TBD

    return tankLevel

def readTankLevel(sensorID):
    tankLevel = -1      # default to "tank not read"

    # select a sensor
    selectSeeLevel(sensorID)

    # collect the bytes returned by the sensor
    slbytes = readSeeLevelBytes()

    # test whether sensor actually responded
    if slbytes == []:
        print("*** sensor did not respond!")
        sensor_errs += 1
    # test whether response stream has expected starting bits "1001----"
    elif slbytes[0] & 0xF0 != 0x90:
        print("*** invalid stream preamble!")
        preamble_errs += 1
    else:
        byte_checksum = sum(slbytes[2:])
        if (byte_checksum - (2+slbytes[1]) % 256 != 0:
            print("***checksum error!")
            checksum_errs += 1
        else:
            # convert data bytes to a tank level
            tankLevel = decodeTankLevel(slbytes[2:], calibration[sensorID])
    
    return tankLevel

powerUpSensors()
tank1_level = readTankLevel(0)     # read level from first sensor
print("test tank level is %d\%" % (tank1_level))
powerDownSensors()
