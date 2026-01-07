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


# Main loop
if __name__ == "__main__":
    rm = pyvisa.ResourceManager()
    k6221 = Keithley6221(rm.open_resource(devices["k6221"]))

    matrix = SwitchMatrix3706(rm.open_resource(devices["matrix"]))

    # kelvinion = KelvinionController(rm.open_resource(devices["kelvinion"]))

    # kelvinion.set_temperature(291,'sample')
    # kelvinion.set_enable('sample',False)

    pins=[1, 2, 3, 4]  # 示例引脚
    matrix.connect(pins)
    currents = [-0.0001, -0.00005, 0.00005, 0.0001]
    v=[]
    for current in currents:
        v.append(k6221.sweep_onestep(current))
        time.sleep(2)
    
    print(currents,v)
    
    '''
    temp_points = [300, 290, 280, 270]
    for T in temp_points:
        kelvinion.set_temperature(T,'sample')
        kelvinion.set_temperature(T,'chamber')
        kelvinion.wait_for_stable(T)
        print(f"[Kelvinion] Temperature stabilized for sample at {kelvinion.get_temperature('F'):.2f} K")

    '''
    '''
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"resistance_measurement_{timestamp}.txt"

    
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ["Time", "Temperature[K]"] + [f"{ch}_R[Ohm](I={cfg['current']}A)" for ch, cfg in channels.items()] +[f"current{ch}={cfg['current']}A" for ch, cfg in channels.items()]
        writer.writerow(header)

        for T in temp_points:
            kelvinion.set_temperature(T,'sample')
            kelvinion.set_temperature(T,'chamber')
            kelvinion.wait_for_stable(T)

            # 获取实际样品温度
            samp_temp = kelvinion.get_sample_temperature('sample')
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