# Keithley-2182-Kelvinion-Resistance-measurement-system

# Hardware preparations
1. GPIB-USB-HS
2. Resistance measure: Keithley 6221 + 2182 
3. Channel control: Keithley 3706A-S, 3730 high density matrix card and 3730 S-T screw terminal block.
4. Temperature control: Kelvinion


## Connecting instruments
1. Connect keithley 2182 to GPIB-USB-HS with GPIB cable.
2. Connect Keithley 6221 and 2182 with RS232 cable and trigger link cable.
3. Connect keithley 3706A to GPIB-USB-HS with GPIB cable.
4. Connect Kelvinion from the Serial port with computer. (GPIB or USB also work)
5. Connect the thermometers, heaters to Kelvinion.

 
## Resistance measure
1. The 2182A must be in RS-232 mode. Set the 2182A to RS-232 mode by pressing SHIFT, RS-232, and setting it to ON.
2. Set the Baud rate, flow control, and terminator characters. These should be 19.2k BAUD, Flow control of XonXoff, and a terminator of CR. The instrument will then return to the home display.
3. Testing the delta mode measurement manually to test the resistance measure system.

## Channel control 
1. Insert the 3730 matrix card into any slot behind 3706.
2. 3730 S-T has 6 rows and 16 columns. Could cover four channels in resistance measurements, and four electrode for each channel.
3. Select 4 rows to connect with Resistance measure 6221 and 2182. 6221 gives out current and 2182 detected the voltage.
4. Connect 16 columns to sample (4 sample channels)
5. Plug the 3730 S-T on the 3730 matrix card.


## Kelvinion

3. Set the sample channel, chamber channel... to monitor the temperature on the instrument pannel.
4. Set the output channels to control the temperature of selected channels.
5. Testing the temperature manually on the instrument channel.

# Software communicating and testing.
1. Edit testing.py with your personal settings like the instrument address, the channel close command of 3706 settings, the current-voltage configuration etc.
2. run testing.py

## Content details
Manage the instruments by pyvisa package, with each self use instrument class.
Some basic command are written, for example, the temperature read and temperature set of different channels of Kelvinion, the delta mode measurement by 6221 and 2182, as well as the specific pin connecting by 3706.

## 3706 settings
because I insert the 3730 matrix card into the 4th slot in the 3706, so the connect_command "self.inst.write(f'channel.close("4{row}{col:02d}")')" starts with 4, like 4110 means: the 4th slot, connect row 1 with column 10. If you put 3730 into other slots, remember to change that value.

The 3730 S-T rows are in the I+ V+ V- I- sequence, for example, pins=[13,14,15,16] means the current is injected in pin 13 and 16, the volage will be detected between pin 14 and 15. So make sure the software match the wiring configuration in 3730 S-T. 

The resistance would be measured in delta mode and shown in terminal.


# Program testing
run gui.py

gui.py is about UI layer, measure_cores.py includes instrument class and basic measuring method, like delta_mode measurement, wait_for_stable, controller.py is to manage the measurement strategy and some complex functions.
...

