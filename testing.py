# main_measurement_program.py

import time
import csv
import pyvisa
import json
from datetime import datetime
import os

from pyvisa.constants import StopBits
from measure_core import KelvinionController, Keithley6221, SwitchMatrix3706

# Load configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "config", "devices.json"), "r") as f:
    devices = json.load(f)
with open(os.path.join(BASE_DIR, "config", "channels.json"), "r") as f:
    channels = json.load(f)
with open(os.path.join(BASE_DIR, "config", "PIDRAMP.json"), "r") as f:
    pidramp = json.load(f)

# Kelvinion Controller
class KelvinionController:
    def __init__(self, resource):
        self.inst = resource
        self.inst.baud_rate = 115200
        self.inst.data_bits = 8
        self.inst.stop_bits = StopBits.one  # 正确写法
        
        #self.inst.write("*RST") 
        print(self.inst.query('*IDN?'))
        # self.inst.write("[SET:ZONE:A:OFF]")#关闭自带的zone模式，使用程序自动确定设置温度点的PID和RAMP速率
        # self.inst.write("[SET:ZONE:B:OFF]")
        # self.inst.write("[SET:LOOP:A:F]") #SET:LOOP:CH:VALUE CH=A/B;VALUE=A-H
        # self.inst.write("[SET:LOOP:B:D]") #设置LOOP A\B分别对应温度计A\B通道
        # self.inst.write('[SET:LIMIT:A:325]')
        # self.inst.write('[SET:LIMIT:B:325]')

    def set_enable(self, loop: str = 'A', enable: bool = True):
        state = 'HIGH' if enable else 'OFF'
        self.inst.write(f"[SET:RANGE:{loop}:{state}]")
        print(f"[Kelvinion] Set loop {loop} enable: {state}")   

    def get_set_temperature(self, channel: str = 'A') -> float:#A\B
        self.inst.write(f"[READ:SETP:{channel}]")
        temp = self.inst.read()
        return float(temp[1:-3])

    def set_sample_ramp(self, target: float):
        ramp = 1
        for entry in pidramp["sample_ramp"]:
            if entry["min"] <= target <= entry["max"]:
                ramp = entry["ramp"]
                break
        self.inst.write(f"[SET:RAMP:A:{ramp}]")
        print(f"[Kelvinion] Set sample RAMP: {ramp}")

    def set_chamber_ramp(self, target: float):
        ramp = 1
        for entry in pidramp["chamber_ramp"]:
            if entry["min"] <= target <= entry["max"]:
                ramp = entry["ramp"]
                break
        self.inst.write(f"[SET:RAMP:B:{ramp}]")
        print(f"[Kelvinion] Set chamber RAMP: {ramp}")

    def set_sample_pid(self, target: float):
        for entry in pidramp["sample_pid"]:
            if entry["min"] <= target <= entry["max"]:
                self.inst.write(f"[SET:PID:A:KP:{entry['P']}]")
                self.inst.write(f"[SET:PID:A:KI:{entry['I']}]")
                self.inst.write(f"[SET:PID:A:KD:0]")
                print(f"[Kelvinion] Set sample PID: P={entry['P']}, I={entry['I']}")
                break

    def set_chamber_pid(self, target: float):
        for entry in pidramp["chamber_pid"]:
            if entry["min"] <= target <= entry["max"]:
                self.inst.write(f"[SET:PID:B:KP:{entry['P']}]")
                self.inst.write(f"[SET:PID:B:KI:{entry['I']}]")
                self.inst.write(f"[SET:PID:B:KD:0]")
                print(f"[Kelvinion] Set chamber PID: P={entry['P']}, I={entry['I']}")
                break

    def set_temperature(self, target: float, loop: str = 'A'):#A\B
        self.inst.write(f"[SET:SETP:{loop}:{target}K]")
        if loop == 'A':
            self.set_sample_ramp(target)
            self.set_sample_pid(target)
        elif loop == 'B':
            self.set_chamber_ramp(target)
            self.set_chamber_pid(target)
        print(f"[Kelvinion] Set loop{loop} to {target:.2f} K")
        

    def get_temperature(self, channel: str = 'F') -> float:#A-H
        self.inst.write(f"[READ:K:{channel}]")
        temp = self.inst.read()
        # if temp =='OVERFLOW' raise error
        return float(temp[1:-3])

    def _tolerance(self, target: float) -> float:
        for entry in pidramp["tolerance_ranges"]:
            if entry["min"] <= target <= entry["max"]:
                return entry["tolerance"]
        return 0.1  # fallback
    '''
    def wait_for_stable(self, target: float, loop: str = 'A', channel: str = 'F'):#loop:A\B, channel:A-H.默认loopA-CHF,loopB-CHD
        tol = self._tolerance(target)
        print(f"[Kelvinion] Waiting for temperature to reach {target:.2f} K (±{tol} K)...")

        # 等待温度首次进入容忍度范围
        while True:
            t = self.get_temperature(channel)
            print(f"[Kelvinion] Temp: {t:.3f} K")
            if abs(t - target) < tol:
                print("[Kelvinion] Temperature entered tolerance range, starting stability check...")
                break
            time.sleep(1)

        # 累计6次在容忍度内
        valid_count = 0
        max_attempts = 60
        attempts = 0
        while valid_count < 6 and attempts < max_attempts:
            t = self.get_temperature(channel)
            print(f"[Kelvinion] Stability Check {valid_count+1}/6 (Attempt {attempts+1}): {t:.3f} K for {loop}")
            if abs(t - target) < tol:
                valid_count += 1
            else:
                print("[Kelvinion] Out of tolerance, waiting...")
            attempts += 1
            time.sleep(0.8)

        if valid_count >= 6:
            print(f"[Kelvinion] Temperature stabilized for {loop}.")
        else:
            raise TimeoutError(f"[Kelvinion] Temperature failed to stabilize for {loop}")
'''
    '''
    def output(self, loop: str = 'A', state = 'on'):
        # 简洁判断
        if str(state).lower() in ['on', 'true', '1'] or state is True:
            state_cmd = 'HIGH'
        elif str(state).lower() in ['off', 'false', '0'] or state is False:
            state_cmd = 'OFF'
        else:
            raise ValueError(f"Unknown state: {state}")
        self.inst.write(f"[SET:RANGE:{loop}:{state_cmd}]")
        print(f"[Kelvinion] Set loop {loop} output: {state}")
'''




# Main loop
if __name__ == "__main__":
    rm = pyvisa.ResourceManager()
    k6221 = Keithley6221(rm.open_resource(devices["k6221"]))

    matrix = SwitchMatrix3706(rm.open_resource(devices["matrix"]))

    kelvinion = KelvinionController(rm.open_resource(devices["kelvinion"]))

    kelvinion.set_temperature(291,'A')
    # kelvinion.set_enable('A',False)

    pins=[1, 2, 3, 4]  # 示例引脚
    matrix.connect(pins)
    current = 1e-4
    V = k6221.delta_measure(current)
    R = V / current
    
    print(f"R={R}Ohm")
    '''
    temp_points = [300, 290, 280, 270]
    for T in temp_points:
        kelvinion.set_temperature(T,'A')
        kelvinion.set_temperature(T,'B')
        kelvinion.wait_for_stable(T)
        print(f"[Kelvinion] Temperature stabilized for A at {kelvinion.get_temperature('F'):.2f} K")

    '''
    '''
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"resistance_measurement_{timestamp}.txt"

    
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ["Time", "Temperature[K]"] + [f"{ch}_R[Ohm](I={cfg['current']}A)" for ch, cfg in channels.items()] +[f"current{ch}={cfg['current']}A" for ch, cfg in channels.items()]
        writer.writerow(header)

        for T in temp_points:
            kelvinion.set_temperature(T,'A')
            kelvinion.set_temperature(T,'B')
            kelvinion.wait_for_stable(T)

            # 获取实际样品温度
            samp_temp = kelvinion.get_sample_temperature('A')
            row = [datetime.now().strftime("%Y/%-m/%-d %-H:%M:%S"), f"{samp_temp:.6e}"]

            for name, cfg in channels.items():
                if not cfg["enabled"]:
                    row.append("--")
                    continue
                
                matrix.connect(cfg["pins"])
                # 用Delta模式测量
                V = k6221.delta_measure(cfg["current"])
                R = V / cfg["current"]
                row.append(f"{R:.6e}")

            writer.writerow(row)
            print(f"[Saved] {row}\n")
    '''
