# Keithley-2182-Kelvinion-Resistance-measurement-system

# Hardware preparations
1. GPIB-USB-HS
2. Resistance measure: Keithley 6221 + 2182 
3. Channel control: Keithley 3706A-S, 3730 high density matrix card and 3730 S-T screw terminal block.
4. Temperature control: Kelvinion

## Resistance measure
1. Connect keithley 2182 to GPIB-USB-HS with GPIB cable.
2. Connect Keithley 6221 and 2182 with RS232 cable and trigger Link cable.
3. The 2182A must be in RS-232 mode. Set the 2182A to RS-232 mode by pressing SHIFT, RS-232, and setting it to ON.
4. You will then be guided to set the Baud rate, flow control, and terminator characters. These should be 19.2k BAUD, Flow control of XonXoff, and a terminator of CR. The instrument will then return to the home display.
5. Testing the delta mode measurement manually to test the resistance measure system.

## Channel control
1. Connect keithley 3706A to GPIB-USB-HS with GPIB cable.
2. Insert the 3730 matrix card into any slot.
3. 3730 S-T has 6 rows and 16 columns. Could cover four channels in resistance measurements, and four electrode for each channel.
4. Select 4 rows to connect with Resistance measure 6221 and 2182. 6221 gives out current and 2182 detected the voltage.
6. Connect 16 columns to sample (4 sample channels)
7. Plug the 3730 S-T on the 3730 matrix card.

## Kelvinion
1. Connect Kelvinion from the Serial port with computer.
2. Connect the thermometers, heaters to Kelvinion
3. Set the sample channel, chamber channel... to monitor the temperature on the instrument pannel.
4. Set the output channels to control the temperature of selected channels.
5. Testing the temperature manually on the instrument channel.


# Software communicating and testing.
1. edit and run testing.py

## Content details
Manage the instruments by pyvisa package, with each self use instrument class.
Some basic command are written, for example, the temperature read and temperature set of different channels of Kelvinion, the delta mode measurement by 6221 and 2182, as well as the specific pin connecting by 3706.


## 3706 setting
because I insert the 3730 matrix card into the 4th slot in the 3706, so the close_command starts with 4, like 4110 means: the 4th slot, connect 1 row with 10 column. If you put 3730 into other slots, remember to change that value.

the pins writes in the I+ V+ V- I- sequence, for example, pins=[13,14,15,16] means the current is generated on 13 and 16, the volaged is detected on 14 and 15. So make sure the software setting wiring in 3730 S-T. 

The resistance would be measured in delta mode and shown in terminal.


# Program testing
...
