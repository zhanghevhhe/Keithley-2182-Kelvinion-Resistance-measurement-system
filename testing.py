# main_measurement_program.py

import time
import csv
import pyvisa
import json
from datetime import datetime
import os

from pyvisa.constants import StopBits


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
    def __init__(self, resource, pidramp_config):
        self.inst = resource
        self.pidramp = pidramp_config # 存储配置
        import threading
        self._lock = threading.Lock()  # 序列化对仪器的所有访问（读写）
        self.inst.baud_rate = 115200
        self.inst.data_bits = 8
        self.inst.stop_bits = StopBits.one
        try:
            # 使用安全查询
            print(self._safe_query('*IDN?'))
        except Exception:
            # 若查询失败仍继续，后续调用会抛异常
            try:
                print(self.inst.query('*IDN?'))
            except Exception:
                pass
        # self.inst.write("[SET:ZONE:A:OFF]")
        # time.sleep(0.05)
        # self.inst.write("[SET:ZONE:B:OFF]")
        # time.sleep(0.05)
        # self.inst.write("[SET:LOOP:A:F]")
        # time.sleep(0.05)
        # self.inst.write("[SET:LOOP:B:D]")
        # time.sleep(0.05)
        # self.inst.write('[SET:LIMIT:A:325]')
        # time.sleep(0.05)
        # self.inst.write('[SET:LIMIT:B:325]')
        # time.sleep(0.05)

    # ---------- 安全读写辅助 ----------
    def _safe_write(self, cmd: str):
        """以锁保护的写操作，保证不同线程写不会交错。"""
        with self._lock:
            self.inst.write(cmd)

    def _safe_query(self, cmd: str):
        """以锁保护的 query 操作，返回原始字符串。"""
        with self._lock:
            return self.inst.query(cmd)
    # -----------------------------------

    def set_enable(self, loop: str = 'A', enable: bool = True):
        state = 'HIGH' if enable else 'OFF'
        self._safe_write(f"[SET:RANGE:{loop}:{state}]")
        print(f"[Kelvinion] Set loop {loop} enable: {state}")   

    def set_sample_ramp(self, target: float, ramp_override: float = None):
        """
        如果提供 ramp_override 则直接写入该速率；
        否则从 pidramp["sample_ramp"] 表中选择对应速率。
        """
        if ramp_override is not None:
            ramp = ramp_override
        else:
            ramp = 1
            for entry in self.pidramp["sample_ramp"]:
                if entry["min"] <= target <= entry["max"]:
                    ramp = entry["ramp"]
                    break
        self._safe_write(f"[SET:RAMP:A:{ramp}]")
        print(f"[Kelvinion] Set sample RAMP: {ramp}")

    def set_chamber_ramp(self, target: float, ramp_override: float = None):
        """
        同上，针对 chamber (loop B)。
        """
        if ramp_override is not None:
            ramp = ramp_override
        else:
            ramp = 1
            for entry in self.pidramp["chamber_ramp"]:
                if entry["min"] <= target <= entry["max"]:
                    ramp = entry["ramp"]
                    break
        self._safe_write(f"[SET:RAMP:B:{ramp}]")
        print(f"[Kelvinion] Set chamber RAMP: {ramp}")

    def set_sample_pid(self, target: float):
        for entry in self.pidramp["sample_pid"]:
            if entry["min"] <= target <= entry["max"]:
                # PID 写入在同一锁区域内进行，避免并发干扰
                with self._lock:
                    self.inst.write(f"[SET:PID:A:KP:{entry['P']}]")
                    time.sleep(0.1)
                    self.inst.write(f"[SET:PID:A:KI:{entry['I']}]")
                    time.sleep(0.1)
                    self.inst.write(f"[SET:PID:A:KD:0]")
                print(f"[Kelvinion] Set sample PID: P={entry['P']}, I={entry['I']}")
                break
    
    def set_chamber_pid(self, target: float):
        for entry in self.pidramp["chamber_pid"]:
            if entry["min"] <= target <= entry["max"]:
                with self._lock:
                    self.inst.write(f"[SET:PID:B:KP:{entry['P']}]")
                    time.sleep(0.1)
                    self.inst.write(f"[SET:PID:B:KI:{entry['I']}]")
                    time.sleep(0.1)
                    self.inst.write(f"[SET:PID:B:KD:0]")
                print(f"[Kelvinion] Set chamber PID: P={entry['P']}, I={entry['I']}")
                break
    
    def set_sample_temperature(self,target: float, ramp_override: float = None):
        self._safe_write(f"[SET:SETP:A:{target}K]")
        # ramp/pid 写入内部已安全序列化
        self.set_sample_ramp(target, ramp_override)
        time.sleep(0.05)
        self.set_sample_pid(target)
    
    def set_chamber_temperature(self,target: float, ramp_override: float = None):
        self._safe_write(f"[SET:SETP:B:{target}K]")
        self.set_chamber_ramp(target, ramp_override)
        time.sleep(0.05)
        self.set_chamber_pid(target)

    def set_sample_range(self, target: float):
        for entry in self.pidramp["sample_range"]:
            if entry["min"] <= target <= entry["max"]:
                self.inst.write(f"[SET:RANGE:A:{entry["range"]}]")
                print(f"[Kelvinion] Set sample range: {entry["range"]}")
                break


    def set_chamber_range(self, target: float):
        for entry in self.pidramp["chamber_range"]:
            if entry["min"] <= target <= entry["max"]:
                self.inst.write(f"[SET:RANGE:B:{entry["range"]}]")
                print(f"[Kelvinion] Set chamber range: {entry["range"]}")
                break
    
    def set_temperature(self, target: float, loop: str = 'A', ramp_override: float = None):
        """
        增加 ramp_override：当 UI 手动设置温度时可传入临时速率覆盖 pidramp 表。
        """
        if loop == 'A':
            self.inst.write(f"[SET:SETP:A:{target}K]")
            time.sleep(0.05)
            self.set_sample_ramp(target, ramp_override)
            time.sleep(0.05)
            self.set_sample_pid(target)
            time.sleep(0.05)
            self.set_sample_range(target)
        elif loop == 'B':
            self.inst.write(f"[SET:SETP:B:{target}K]")
            time.sleep(0.05)
            self.set_chamber_ramp(target, ramp_override)
            time.sleep(0.05)
            self.set_chamber_pid(target)
            time.sleep(0.05)
            self.set_chamber_range(target)
        print(f"[Kelvinion] Set loop {loop} to {target:.2f} K (ramp_override={ramp_override})")
        
    def read_temperatures(self):
        """
        原子性读取样品(F)和腔体(D)温度，返回 (sample_temp, chamber_temp)。
        在一个锁内连续 query，避免被其它线程的读写打断造成错位返回。
        """
        with self._lock:
            raw_f = self.inst.query(f"[READ:K:F]")
            # 确保返回格式解析安全，尽量容错
            try:
                t_f = float(raw_f[1:-3])
            except Exception:
                try:
                    t_f = float(raw_f)
                except Exception:
                    t_f = float('nan')
            raw_d = self.inst.query(f"[READ:K:D]")
            try:
                t_d = float(raw_d[1:-3])
            except Exception:
                try:
                    t_d = float(raw_d)
                except Exception:
                    t_d = float('nan')
        return t_f, t_d

    def get_set_temperature(self, channel: str = 'A') -> float:#A\B
        with self._lock:
            raw = self.inst.query(f"[READ:SETP:{channel}]")
        try:
            return float(raw[1:-3])
        except Exception:
            try:
                return float(raw)
            except Exception:
                return float('nan')
 
    def get_temperature(self, channel: str = 'F') -> float:
        # 为兼容现有调用，优先使用 read_temperatures 获取一致快照
        if channel == 'F':
            t_f, _ = self.read_temperatures()
            return t_f
        elif channel == 'D':
            _, t_d = self.read_temperatures()
            return t_d
        else:
            # 其它 channel 回退到单次安全查询
            raw = self._safe_query(f"[READ:K:{channel}]")
            try:
                return float(raw[1:-3])
            except Exception:
                try:
                    return float(raw)
                except Exception:
                    return float('nan')

    def _tolerance(self, target: float) -> float:
        for entry in self.pidramp["tolerance_ranges"]:
            if entry["min"] <= target <= entry["max"]:
                return entry["tolerance"]
        return 0.1

    def wait_for_stable(self, target: float, loop: str = 'A', is_running_checker=None):
        tol = self._tolerance(target)
        print(f"[Kelvinion] Waiting for temperature to reach {target:.2f} K (±{tol} K)...")
        while True:
            if is_running_checker and not is_running_checker():
                print("[Kelvinion] wait_for_stable aborted by user.")
                return
            interruptible_sleep(0.8)
            # 使用一次性原子读取避免交错
            t, _ = self.read_temperatures()
            if abs(t - target) < tol:
                print("[Kelvinion] Temperature entered tolerance range...")
                break
            if not interruptible_sleep(1, is_running_checker):
                print("[Kelvinion] wait_for_stable aborted by user (sleep phase).")
                return

        valid_count = 0
        while valid_count < 6:
            if is_running_checker and not is_running_checker():
                print("[Kelvinion] wait_for_stable aborted by user.")
                return
            interruptible_sleep(0.8)
            t, _ = self.read_temperatures()
            print(f"[Kelvinion] Stability Check {valid_count+1}/6: {t:.3f} K")
            if t - target < tol and target - t < tol:
                valid_count += 1
            else:
                valid_count = 0
            if not interruptible_sleep(1, is_running_checker):
                print("[Kelvinion] wait_for_stable aborted by user (sleep phase).")
                return
        print(f"[Kelvinion] Temperature stabilized for {loop}.")


class Keithley6221:
    """
    Keithley 6221+ Keithley 2182 源表方法。源表通过RS232+TRIGGER线互联，GPIB线只连接6221
    """
    def __init__(self, resource):
        self.inst = resource
        self.inst.write("*RST")
        self.inst.write('*CLS')
        print("[6221] Initialized")

    def reading_latest(self)->float:
        self.inst.write(':SENSe:DATA:LATest?')
        time.sleep(0.01)
        return float(self.inst.read().split(',')[0])
    
    def reading_fresh(self)->float:
        self.inst.write(':SENSe:DATA:FRESh?')
        time.sleep(0.01)
        return float(self.inst.read())
     

    def delta_measure(self, current, Vrange = '10mV'):
        if Vrange == '10mV':
            V = '0.01'
        elif Vrange == '100mV':
            V = '0.1'
        elif Vrange == '1V':
            V = '1'
        elif Vrange == '10V':
            V = '10'
        self.inst.write('*RST')
        self.inst.write('*CLS')
        self.inst.write('OUTPut:LTEarth OFF')
        self.inst.write('OUTPUT:ISHIELD OLOW')
        self.inst.write('UNIT:VOLT:DC V')
        self.inst.write('SENS:AVER:TCON MOV')
        self.inst.write('SENS:AVER:WIND 0.1')
        self.inst.write('SENS:AVER:COUN 6')
        self.inst.write('SENS:AVER ON')
        self.inst.write('SYSTEM:COMMUNICATE:SERIAL:SEND "VOLT:NPLC 5"')
        self.inst.write(f'SYSTEM:COMMUNICATE:SERIAL:SEND "VOLT:RANG {V}"')
        self.inst.write('CURRent:COMPliance 10')
        self.inst.write(f'SOURCE:DELTA:HIGH {current:.3e}')
        self.inst.write(f'SOURCE:DELTA:LOW {-current:.3e}')
        self.inst.write('SOURCE:DELTA:DELAY 0.1')
        self.inst.write('SOURCE:DELTA:COUNT INF')
        self.inst.write('SOURCE:DELTA:ARM')
        self.inst.write('INITIATE:IMMEDIATE')

        time.sleep(5)
        v = self.reading_latest()
        # self.inst.write(':SENSe:DATA:LATest?')
        # time.sleep(0.01)
        # v = float(self.inst.read_bytes(128))

        self.inst.write('SOURCE:SWEEP:ABORT') #关闭

        print(f"[6221] Delta Avg V: {v:.6e} V")
        return v

class SwitchMatrix3706:
    """
    Keithley 3706矩阵开关
    """
    def __init__(self, resource):
        self.inst = resource
        self.inst.write('reset()')
        self.inst.write('channel.open("allslots")')
        print("[3706] Initialized")

    def open_all(self):
        self.inst.write('channel.open("allslots")')
        print("[3706] All channels opened (disconnected)")

    def connect(self, pins):
        #示例：pins=[1, 2, 3, 4]
        self.open_all()
        for row, col in enumerate(pins, 1):
            self.inst.write(f'channel.close("4{row}{col:02d}")')
        print(f"[3706] Connected pins: {pins}")




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
