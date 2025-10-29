import os
import json
import threading
import time
import pyvisa
from pyvisa.constants import StopBits
import random
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import numpy as np

# --- 严格遵循 main.py 的真实仪器控制类 ---

def interruptible_sleep(total_sec, is_running_checker=None, interval=0.2):
    elapsed = 0
    while elapsed < total_sec:
        if is_running_checker and not is_running_checker():
            return False
        time.sleep(min(interval, total_sec - elapsed))
        elapsed += interval
    return True

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
            if t - target < tol and target - t < tol:
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


class MeasurementSystem(QObject):
    current_temp_changed = pyqtSignal(float)  # 保持向后兼容
    sample_temp_changed = pyqtSignal(float)   # 样品温度（F通道）
    chamber_temp_changed = pyqtSignal(float) # 样品腔温度（D通道）
    error_occurred = pyqtSignal(str)          # 错误信息信号
    warning_occurred = pyqtSignal(str)        # 警告信息信号

    def __init__(self):
        super().__init__()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, "config", "devices.json"), "r") as f:
            self.devices = json.load(f)
        with open(os.path.join(base_dir, "config", "channels.json"), "r") as f:
            self.channels = json.load(f)
        with open(os.path.join(base_dir, "config", "PIDRAMP.json"), "r") as f:
            self.pidramp = json.load(f)
        
        # 为通道分配持久化的颜色
        colors = ['#E6194B', '#3CB44B', '#4363D8', '#F58231'] # 红, 绿, 蓝, 橙
        for i, ch in enumerate(self.channels):
            self.channels[ch]['last_resistance'] = '--'
            self.channels[ch]['color'] = colors[i % len(colors)]

        self.save_path = base_dir
        self.lock = threading.Lock()
        
        self.rm = None
        self.kelvinion = None
        self.k6221 = None
        self.matrix = None
        
        # 温度监控定时器
        self.temp_timer = QTimer()
        self.temp_timer.timeout.connect(self._update_hardware_temperatures)
        self.temp_timer.start(1000)  # 每秒更新一次温度
        
        self.initialize_instruments()

    def get_available_sources(self):
        """返回已成功初始化的可用仪器列表。"""
        sources = []
        sources.append("Keithley 6221")
        sources.append("Kelvinion")
        return sources

    def initialize_instruments(self):
        try:
            print("Initializing instruments...")
            self.rm = pyvisa.ResourceManager()
            # 初始化时传入pidramp配置
            self.kelvinion = KelvinionController(self.rm.open_resource(self.devices["kelvinion"]), self.pidramp)
            self.k6221 = Keithley6221(self.rm.open_resource(self.devices["k6221"]))
            self.matrix = SwitchMatrix3706(self.rm.open_resource(self.devices["matrix"]))
            print("All instruments initialized successfully.")
        except Exception as e:
            error_msg = f"Error initializing instruments: {e}. Running in simulation mode."
            print(error_msg)
            self.error_occurred.emit(error_msg)
            self.rm = self.kelvinion = self.k6221 = self.matrix = None



    def save_channels_config(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "config", "channels.json")
        with open(path, "w") as f:
            json.dump(self.channels, f, indent=4, sort_keys=True)

    def set_save_path(self, path):
        self.save_path = path

    def update_last_resistance(self, channel_name, resistance):
        """[重构] 更新指定通道的最新电阻值。"""
        if channel_name in self.channels:
            self.channels[channel_name]['last_resistance'] = f"{resistance:.6e}"

    def update_channels(self, new_channels_data):
        """[重构] 用新的配置数据更新内部channels字典并保存。
        修改为深度更新，以保留 'last_resistance' 等不在对话框中管理的键。
        """
        for ch_name, ch_data in new_channels_data.items():
            if ch_name in self.channels:
                self.channels[ch_name].update(ch_data)
            else:
                self.channels[ch_name] = ch_data
        self.save_channels_config()

    def get_csv_header(self):
        """动态生成CSV文件的表头。"""
        header = ["Timestamp", "Temperature[K]"]
        channel_names = sorted(self.channels.keys())
        for ch_name in channel_names:
            header.append(f"Resistance_{ch_name}[Ohm]")
        return header

    def get_channel_info_for_display(self, channel_name):
        """[重构] 获取单个通道用于UI显示的信息（标题）。"""
        if channel_name not in self.channels:
            return {"title": "Unknown Channel"}
            
        ch_config = self.channels[channel_name]
        is_enabled = ch_config.get('enabled', False)
        status_text = "Enabled" if is_enabled else "Disabled"
        current = ch_config.get('current', 'N/A')
        last_r = ch_config.get('last_resistance', '--')
        
        title = f"{channel_name}: {status_text} | I = {current} A | R = {last_r}"
        
        return {
            "title": title,
            "enabled": is_enabled
        }

    
    def get_sample_temperature(self):
        """获取样品温度（F通道）"""
        # 保留兼容接口，但优先使用一次性读取（避免交叉读取）
        t_f, _ = self.get_temperatures()
        return t_f

    def get_chamber_temperature(self):
        """获取样品腔温度（D通道）"""
        _, t_d = self.get_temperatures()
        return t_d

    def get_temperatures(self):
        """
        原子性获取样品(F)和腔体(D)温度，返回 (sample_temp, chamber_temp)。
        UI / 外部调用应优先使用此接口避免并发交错。
        """
        try:
            if self.kelvinion:
                return self.kelvinion.read_temperatures()
        except Exception as e:
            print(f"[MeasurementSystem] get_temperatures error: {e}")
        # 回退：模拟或错误时返回 NaN
        return float('nan'), float('nan')
 
    def _update_hardware_temperatures(self):
        """
        定期从硬件获取温度数据并发送信号。
        这个方法由定时器每秒调用一次。
        """
        try:
            # 原子性一次性读取样品与腔体温度，避免交叉读写导致错位或交替值
            sample_temp, chamber_temp = self.get_temperatures()
             
            # 发送温度信号
            self.sample_temp_changed.emit(sample_temp)
            self.chamber_temp_changed.emit(chamber_temp)
            self.current_temp_changed.emit(sample_temp)  # 保持向后兼容
        except Exception as e:
            error_msg = f"Temperature reading error: {e}"
            print(f"[Temperature Update] {error_msg}")
            self.error_occurred.emit(error_msg)
            # 出错时发送默认值
            self.sample_temp_changed.emit(0.0)
            self.chamber_temp_changed.emit(0.0)
            self.current_temp_changed.emit(0.0)

    def measure_single_channel(self, ch_name, channel_config):


        # --- 使用你提供的 delta_measure 方法进行真实测量 ---
        try:
            current = float(channel_config['current'])
            Vrange = channel_config.get('voltage_range', '1V')
            pins = channel_config.get('pins', [])
            
            if not pins:
                print(f"Warning: No pins configured for channel {ch_name}. Skipping.")
                return float('nan')

            # 1. 使用 connect 方法连接指定通道
            self.matrix.connect(pins)
            print(f"Connected pins: {pins}")
            
            # 2. 调用 delta_measure 获取电压
            voltage = self.k6221.delta_measure(current, Vrange)
            print(f"Voltage and current: {voltage}, {current}")
            # 3. 计算电阻
            if abs(current) < 1e-15:
                resistance = float('inf')
            else:
                resistance = voltage / current
            
            print(f"[System] Measured R = {resistance:.6e} Ohm for channel {ch_name} (V={voltage:.6e}, I={current:.2e})")

            return resistance
        
        except Exception as e:
            error_msg = f"Measurement error on channel {ch_name}: {e}"
            print(f"FATAL ERROR during measurement of channel {ch_name}: {e}")
            self.error_occurred.emit(error_msg)
            # 如果delta_measure中途出错，尝试中止扫描
            if self.k6221:
                try:
                    self.k6221.inst.write('SOURCE:SWEEP:ABORT')
                    print("[K6221] Sent ABORT command due to error.")
                except Exception as abort_e:
                    print(f"Error sending ABORT command: {abort_e}")
            return float('nan')
        
        finally:
            # 无论成功与否，最后都断开所有开关 (重要安全步骤)
            if self.matrix:
                try:
                    self.matrix.open_all()
                except Exception as open_all_e:
                    print(f"Error in finally block calling open_all: {open_all_e}")

    def shutdown_instruments(self):
        print("Shutting down instruments...")
        if self.kelvinion:
            self.kelvinion.inst.close()
        if self.k6221:
            self.k6221.inst.close()


    def load_pidramp(self, path: str) -> bool:
        """
        在运行时加载指定的 PIDRAMP JSON 文件并应用到当前 MeasurementSystem。

        成功返回 True，失败会抛出异常或返回 False。
        """
        if not path:
            raise ValueError("No path provided for PIDRAMP file.")
        if not os.path.exists(path):
            raise FileNotFoundError(f"PIDRAMP file not found: {path}")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 简单校验一些期望的键，若无则仍接受但发出警告
            expected_keys = ['sample_ramp', 'chamber_ramp', 'sample_pid', 'chamber_pid', 'tolerance_ranges']
            has_expected = any(k in data for k in expected_keys)
            self.pidramp = data

            # 如果已初始化 kelvinion 实例，更新其 pidramp 引用
            if getattr(self, 'kelvinion', None) is not None:
                try:
                    self.kelvinion.pidramp = data
                except Exception:
                    pass

            if not has_expected:
                # 发出警告信号，告知加载的文件可能不是完整的 pidramp 配置
                try:
                    self.warning_occurred.emit('Loaded PIDRAMP file missing some expected keys.')
                except Exception:
                    pass

            return True
        except Exception as e:
            # 转发错误到 UI
            try:
                self.error_occurred.emit(f'Failed to load PIDRAMP: {e}')
            except Exception:
                pass
            raise



    def set_ramp_for_loop(self, loop: str, ramp: float):
        """
        UI 若只想单独设置 ramp（不改 setpoint），可调用此接口。
        """
        if not self.kelvinion:
            print("[Simulation] set_ramp_for_loop called in simulation mode.")
            return
        try:
            # 尝试读取当前设定的 setpoint，再写入对应回路的 ramp
            current_set = None
            try:
                current_set = self.kelvinion.get_set_temperature('A' if loop == 'A' else 'B')
            except Exception:
                # 如果读取失败，传入 300K 作为占位 target 用于查表（但我们使用 ramp_override 所以不影响）
                current_set = 300.0
            if loop == 'A':
                self.kelvinion.set_sample_ramp(current_set, ramp_override=ramp)
            elif loop == 'B':
                self.kelvinion.set_chamber_ramp(current_set, ramp_override=ramp)
            else:
                print(f"[System] Invalid loop {loop} for setting ramp.")
        except Exception as e:
            msg = f"Failed to set ramp for loop {loop}: {e}"
            print(msg)
            self.error_occurred.emit(msg)