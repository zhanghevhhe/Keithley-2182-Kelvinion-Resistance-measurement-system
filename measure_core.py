import os
import json
import threading
import time
import pyvisa
from pyvisa.constants import StopBits
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from abc import ABC, abstractmethod

# --- 严格遵循 main.py 的真实仪器控制类 ---


def interruptible_sleep(total_sec, is_running_checker=None, interval=0.2):
    elapsed = 0
    while elapsed < total_sec:
        if is_running_checker and not is_running_checker():
            return False
        time.sleep(min(interval, total_sec - elapsed))
        elapsed += interval
    return True

class TempController(ABC):
    def __init__(self, resource, pidramp_config):
        self.inst = resource
        self.pidramp = pidramp_config
        self._lock = threading.Lock()
        self.temperatures = (0.0, 0.0)
        self.powers = (0.0, 0.0)
        # 可配置的通道映射，方便以后更换通道命名或仪器


    # 注意：简化策略——只接受 'sample' 或 'chamber' 两个角色，
    # 并直接从 `channel_map` 中读取对应的 loop 与 temp channel。

    # --- 必须由子类实现的底层指令 (抽象方法) ---
    @abstractmethod
    def _send_setp(self, loop: str, target: float): pass

    @abstractmethod
    def _send_ramp(self, loop: str, ramp_val: float): pass

    @abstractmethod
    def _send_pid(self, loop: str, p: float, i: float, d: float): pass

    @abstractmethod
    def _send_range(self, loop: str, range_val: str): pass

    @abstractmethod
    def _query_set_temp(self, channel: str) -> float: pass

    @abstractmethod
    def _query_temp(self, channel: str) -> float: pass

    @abstractmethod
    def _query_power(self, loop: str) -> float: pass

    # --- 通用逻辑：所有仪器通用的算法，直接复用 ---
    def read_set_temperature(self, loop: str = 'sample') -> float:
        """通用读取设定温度逻辑；loop 为 'sample' 或 'chamber'"""
        return self._query_set_temp(loop)

    def set_ramp(self, target: float, loop: str = 'sample', ramp_override: float = None):
        """通用 Ramp 设置逻辑；loop 为 'sample' 或 'chamber'"""
        ramp = ramp_override if ramp_override is not None else 1.0
        config_key = "sample_ramp" if loop == 'sample' else "chamber_ramp"
        if ramp_override is None:
            for entry in self.pidramp.get(config_key, []):
                if entry["min"] <= target < entry["max"]:
                    ramp = entry.get("ramp", ramp)
                    break
        self._send_ramp(loop, ramp)
    
    def set_pid(self, target: float, loop: str = 'sample'):
        """通用 PID 设置逻辑；loop 为 'sample' 或 'chamber'"""
        config_key = "sample_pid" if loop == 'sample' else "chamber_pid"
        for entry in self.pidramp.get(config_key, []):
            if entry["min"] <= target < entry["max"]:
                self._send_pid(loop, entry.get('P', 10), entry.get('I', 1), entry.get('D', 0))
                break
    
    def set_range(self, target: float, loop: str = 'sample'):
        """通用 Range 设置逻辑；loop 为 'sample' 或 'chamber'"""
        config_key = "sample_range" if loop == 'sample' else "chamber_range"
        for entry in self.pidramp.get(config_key, []):
            if entry["min"] <= target < entry["max"]:
                self._send_range(loop, entry.get('range'))
                break

    def set_temperature(self, target: float, loop: str = 'sample', ramp_override: float = None):
        """通用设温逻辑：自动查找并设置 PID、Ramp、Range
        loop 可传 'sample'/'chamber' 或底层 loop id
        """
        self._send_setp(loop, target)
        self.set_ramp(target, loop, ramp_override)
        self.set_pid(target, loop)
        self.set_range(target, loop)
        print(f"[{self.__class__.__name__}] Loop {loop} configured for {target} K")

    def _tolerance(self, target: float) -> float:
        for entry in self.pidramp["tolerance_ranges"]:
            if entry["min"] <= target < entry["max"]:
                return entry["tolerance"]
        return 0.1
    #--------------------------------------------------
    # 其他功能语句

    def wait_for_stable(self, target: float, loop: str = 'sample', is_running_checker=None):
        tol = self._tolerance(target)
        print(f"[TempCon] Waiting for temperature to reach {target:.2f} K (±{tol} K)...")
        while True:
            if is_running_checker and not is_running_checker():
                print("[TempCon] wait_for_stable aborted by user.")
                return
            interruptible_sleep(0.8)
            # 从属性获取温度，避免交叉读写
            t = self.get_sample_temperature() if loop == 'sample' else self.get_chamber_temperature()
            if t - target < tol and target - t < tol:
                print("[TempCon] Temperature entered tolerance range...")
                break
            if not interruptible_sleep(1, is_running_checker):
                print("[TempCon] wait_for_stable aborted by user (sleep phase).")
                return
        
        valid_count = 0
        while valid_count < 6:
            if is_running_checker and not is_running_checker():
                print("[TempCon] wait_for_stable aborted by user.")
                return
            interruptible_sleep(0.8)
            t = self.get_sample_temperature() if loop == 'sample' else self.get_chamber_temperature()
            print(f"[TempCon] Stability Check {valid_count+1}/6: {t:.3f} K")
            if t - target < tol and target - t < tol:
                valid_count += 1
            else:
                valid_count = 0
            if not interruptible_sleep(1, is_running_checker):
                print("[TempCon] wait_for_stable aborted by user (sleep phase).")
                return
        print(f"[TempCon] Temperature stabilized for {loop}.")

    def get_sample_power(self): return self.powers[0]
    def get_chamber_power(self): return self.powers[1]
    def get_sample_temperature(self): return self.temperatures[0]
    def get_chamber_temperature(self): return self.temperatures[1]

class KelvinionController(TempController):
    def __init__(self, resource, pidramp_config):
        super().__init__(resource, pidramp_config)
        # 串口基础设置
        self.inst.baud_rate = 115200
        self.inst.data_bits = 8
        # ... 其他初始化 ...
        # 'sample' or 'chamber'
        self.channel_map = {
            'sample_loop': 'A',
            'chamber_loop': 'B',
            'sample_temp_channel': 'F',
            'chamber_temp_channel': 'D'
        }

    def _safe_query(self, cmd: str):
        with self._lock:
            return self.inst.query(cmd)

    def _safe_write(self, cmd: str):
        with self._lock:
            self.inst.write(cmd)

    # --- 实现父类要求的底层指令 ---
    def _send_setp(self, loop: str, target: float):
        loopname = self.channel_map.get(f"{loop}_loop")
        self._safe_write(f"[SET:SETP:{loopname}:{target}K]")

    def _send_ramp(self, loop: str, ramp_val: float):
        loopname = self.channel_map.get(f"{loop}_loop")
        self._safe_write(f"[SET:RAMP:{loopname}:{ramp_val}]")

    def _send_pid(self, loop: str, p: float, i: float, d: float):
        # 针对 Kelvinion 需要分两次写入的特性
        loopname = self.channel_map.get(f"{loop}_loop")
        with self._lock:
            self.inst.write(f"[SET:PID:{loopname}:KP:{p}]")
            time.sleep(0.1)
            self.inst.write(f"[SET:PID:{loopname}:KI:{i}]")

    def _send_range(self, loop: str, range_val: str):
        loopname = self.channel_map.get(f"{loop}_loop")
        self._safe_write(f"[SET:RANGE:{loopname}:{range_val}]")

    def _query_temp(self, channel: str) -> float:
        channelname = self.channel_map.get(f"{channel}_temp_channel")
        raw = self._safe_query(f"[READ:K:{channelname}]")
        return float(raw[1:-3]) # 剥离 [ 和 ]K

    def _query_power(self, loop: str) -> float:
        loopname = self.channel_map.get(f"{loop}_loop")
        raw = self._safe_query(f"[READ:POWER:{loopname}]")
        return float(raw[1:-3])

    def _query_set_temp(self, loop: str) -> float:
        loopname = self.channel_map.get(f"{loop}_loop")
        raw = self._safe_query(f"[READ:SETP:{loopname}]")
        return float(raw[1:-3])

    def read_temperatures(self):
        """重写原子读取，优化性能"""
        sample_temp = self._query_temp('sample')
        chamber_temp = self._query_temp('chamber')
        self.temperatures = (sample_temp, chamber_temp)
        return self.temperatures

    def read_powers(self):
        """重写原子读取，优化性能"""
        p_a = self._query_power('sample')
        p_b = self._query_power('chamber')
        self.powers = (p_a, p_b)
        return self.powers

class Model24CController(TempController):
    def __init__(self, resource, pidramp_config):
        super().__init__(resource, pidramp_config)
        # 串口基础设置
        self.inst.baud_rate = 9600
        self.inst.data_bits = 8
        self.inst.stop_bits = StopBits.one
        # ... 其他初始化 ...
        self.channel_map = {
            'sample_loop': 'A',
            'chamber_loop': 'B',
            'sample_temp_channel': 'F',
            'chamber_temp_channel': 'D'
        }

    def _safe_query(self, cmd: str):
        with self._lock:
            return self.inst.query(cmd)

    def _safe_write(self, cmd: str):
        with self._lock:
            self.inst.write(cmd)

    # --- 实现父类要求的底层指令 ---
    def _send_setp(self, loop: str, target: float):
        pass

    def _send_ramp(self, loop: str, ramp_val: float):
        pass

    def _send_pid(self, loop: str, p: float, i: float, d: float):
        pass

    def _send_range(self, loop: str, range_val: str):
        pass

    def _query_temp(self, channel: str) -> float:
        pass

    def _query_power(self, loop: str) -> float:
        pass

    def _query_set_temp(self, channel: str) -> float:
        pass



class Keithley6221:
    """
    Keithley 6221 (Source) + Keithley 2182 (Nanovoltmeter) 组合控制类。
    硬件连接假设：
    1. PC -> GPIB -> 6221
    2. 6221 -> RS232 + Trigger Link -> 2182
    """
    def __init__(self, resource):
        """
        :param resource: pyvisa resource object (已经打开的资源实例)
        """
        self.inst = resource
        # 初始化仪器状态
        self.reset()
        print("[System] Initialized Keithley 6221 + 2182 system")

    def reset(self):
        """复位仪器并清除状态寄存器"""
        self.inst.write("*RST")
        self.inst.write('*CLS')
        time.sleep(0.5) # 给仪器一点复位时间

    def _send_2182(self, command):
        """
        辅助函数：通过 6221 的串口透传指令给 2182
        """
        # 6221 要求串口指令用双引号包裹
        cmd_str = f'SYSTEM:COMMUNICATE:SERIAL:SEND "{command}"'
        self.inst.write(cmd_str)

    def configure_system_common(self):
        """
        配置通用的系统设置 (Shielding, Earth, Units)
        """
        self.inst.write('OUTPut:LTEarth OFF')   # 关闭 Low Terminal Earth
        self.inst.write('OUTPUT:ISHIELD OLOW')  # Inner Shield Output Low
        self.inst.write('UNIT:VOLT:DC V')       # 设置单位

    def configure_2182_filter(self, count=5, window=0.01, filter_type='MOV'):
        """
        配置 2182 的数字滤波器设置
        """
        self._send_2182("VOLT:CHAN1:LPAS OFF")         # 关闭模拟低通滤波
        
        self._send_2182(f"VOLT:CHAN1:DFIL:COUN {count}")
        self._send_2182(f"VOLT:CHAN1:DFIL:WIND {window}")
        self._send_2182(f"VOLT:CHAN1:DFIL:TCON {filter_type}")
        self._send_2182("VOLT:CHAN1:DFIL:STAT ON")     # 开启数字滤波
        print(f"[2182] Filter configured: Count={count}, Window={window}")

    def get_reading(self, mode='FETCH'):
        """
        获取读数。
        
        :param mode: 读取模式，支持 'FETCH' (获取最新测量结果), 'LATEST' (获取最新存储读数), 
                     或 'FRESH' (等待新的测量读数)。
        :raises ValueError: 如果传入的 mode 无效。
        """
        # 定义允许的模式及其对应的 SCPI 命令，提高健壮性
        ALLOWED_MODES = {
            'FETCH': ':FETC?',           # 获取 INIT/ARM 序列完成后的结果 (推荐用于同步测量)
            'LATEST': ':SENSe:DATA:LATest?', # 获取存储器中最新的读数
            'FRESH': ':SENSe:DATA:FRESh?'    # 请求新读数并等待其完成
        }
        
        mode_upper = mode.upper()
        
        if mode_upper not in ALLOWED_MODES:
            # 模式无效时抛出明确的错误
            raise ValueError(f"Invalid reading mode '{mode}'. Must be one of: {', '.join(ALLOWED_MODES.keys())}")
            
        cmd = ALLOWED_MODES[mode_upper]
        
        try:
            raw_data = self.inst.query(cmd)
            # 数据格式通常是 "数值, 状态, ...", 我们只取第一个
            return float(raw_data.split(',')[0])
        except Exception as e:
            print(f"Error reading data using command '{cmd}': {e}")
            raise

    def measure_dc_current(self, current, compliance=25, nplc=5, delay_s=1.0):
        """
        执行单点 DC 电流输出并测量电压 (Sweep One Step)
        
        *** 关键优化：采用 INIT + FETC? 确保读取的是新测量值 ***

        :param current: 输出电流 (Amp)
        :param compliance: 顺从电压 (Volt)
        :param nplc: 积分周期 (Number of Power Line Cycles), 5 是慢速高精度
        :param delay_s: 输出电流稳定等待时间（秒）。通过 SOUR:DELAY 实现，比 time.sleep 更可靠。
        """
        # 1. 完整设置仪器状态
        self.reset()
        self.configure_system_common()
        
        # 配置 2182 (测量)
        
        
        self.configure_2182_filter(count=5, window=0.01)
        self._send_2182(f"VOLT:NPLC {nplc}")
        self._send_2182("VOLT:RANG:AUTO ON")

        # 配置 6221 (源)
        self.inst.write(f'CURR:COMP {compliance}')
        self.inst.write(':SOUR:CURR:RANG:AUTO ON')
        
        # 设置电流和源延时（等待稳定时间）
        self.inst.write(f':SOUR:CURR {current:.3e}')
        self.inst.write('OUTPUT ON')
        self.inst.write('*OPC')

        self._send_2182('TRAC:CLE') 

        time.sleep(delay_s)  # 确保输出开启命令生效

        self.inst.write('INITIATE:IMMEDIATE')
        
        try:
            self.inst.write('SYSTEM:COMMUNICATE:SERIAL:SEND ":SENSe:DATA:FRESh?"')
            self.inst.write('SYSTEM:COMMUNICATE:SERIAL:ENTER?')
            time.sleep(0.5)
            raw_data = self.inst.read()
            print(f'raw data = {raw_data}')
            voltage = float(raw_data.split(',')[0])
            
            print(f"[DC - Reliable] Measurement complete. V={voltage:.6e} V")
            return voltage
        except Exception as e:
            print(f"Error during DC measurement fetch: {e}")
            raise
        finally:
            # 单点测量完成后，关闭输出是安全惯例
            self.inst.write('SOURCE:SWEEP:ABORT')
            self.inst.write('OUTP OFF')

    def measure_delta_mode(self, current, voltage_range=0.01, compliance=10, duration=5.0, ave_count=13):
        """
        执行 Delta 模式测量 (正负电流交替消除热电势)
        
        *** 优化：TRAC:CLE 确保平均值基于本次测量 ***
        
        :param current: 电流幅值 (Amp)
        :param voltage_range: 2182 电压量程 (可以是字符串 '10mV' 或 浮点数 0.01)
        :param compliance: 顺从电压
        :param duration: 测量持续时间 (秒)
        :param ave_count: 2182 平均计数
        """
        # 处理电压量程参数
        v_range_val = voltage_range
        if isinstance(voltage_range, str):
            v_map = {'10mV': 0.01, '100mV': 0.1, '1V': 1, '10V': 10}
            v_range_val = v_map.get(voltage_range, 0.01)

        # Delta 模式必须从复位状态开始以确保同步
        self.reset()
        self.configure_system_common()
        
        # 配置 2182
        self._send_2182(f"VOLT:RANG {v_range_val}")
        self._send_2182("VOLT:NPLC 5")
        
        # 2182 Average 设置 (这是 Delta 模式的关键配合)
        self.inst.write('SENS:AVER:TCON MOV')
        self.inst.write('SENS:AVER:WIND 0.1')
        self.inst.write(f'SENS:AVER:COUN {ave_count}')
        self.inst.write('SENS:AVER ON')

        # 配置 6221 Delta 参数
        self.inst.write(f'CURRent:COMPliance {compliance}')
        self.inst.write(f'SOURCE:DELTA:HIGH {current:.3e}')
        self.inst.write(f'SOURCE:DELTA:LOW {-current:.3e}')
        self.inst.write('SOURCE:DELTA:DELAY 0.1') # 电流反转后的稳定延时
        self.inst.write('SOURCE:DELTA:COUNT INF') # 无限循环，直到我们手动停止
        
        # 启动 Delta
        print("[Delta] Arming and initiating Delta mode...")
        
        # 优化点: 清空 2182 测量缓冲区，确保平均值基于本次测量
        self._send_2182('TRAC:CLE') 
        
        self.inst.write('SOURCE:DELTA:ARM')
        self.inst.write('INITIATE:IMMEDIATE')

        # 等待测量数据稳定，让 Delta 模式运行一段时间以进行充分的平均
        time.sleep(duration)
        
        try:
            # 读取 Delta 读数 (LATEST 是 2182 自动计算的平均值)
            voltage = self.get_reading(mode='LATEST')
        finally:
            # 停止 Delta 模式并关闭输出
            self.inst.write('SOURCE:SWEEP:ABORT')
            self.inst.write('OUTPUT OFF')
            
        print(f"[Delta] Result V: {voltage:.6e} V (Avg over {duration}s)")
        return voltage

    def close(self):
        """安全关闭"""
        try:
            self.inst.write('OUTPUT OFF')
        except:
            pass
        # 注意：这里不关闭 resource，因为 resource 是外部传入的，应由外部关闭

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
        try:
            self.inst.write('channel.open("allslots")')
            print("[3706] All channels opened (disconnected)")
        except Exception as e:
            print(f"[3706] Error opening all channels: {e}")


    def connect(self, pins):
        # 示例：pins=[1, 2, 3, 4]
        self.open_all()
        cmds = []
        for row, col in enumerate(pins, 1):
            chan_str = f'4{row}{col:02d}'
            cmds.append(chan_str)

        # DEBUG: 列出将要闭合的通道 id，便于排查映射问题
        print(f"[3706] Connecting pins {pins} -> channels {cmds}")
        for chan_str in cmds:
            try:
                self.inst.write(f'channel.close("{chan_str}")')
            except Exception as e:
                print(f"[3706] Error writing channel.close for {chan_str}: {e}")


class MeasurementSystem(QObject):
    sample_temp_changed = pyqtSignal(float)    # 样品温度（F通道）
    chamber_temp_changed = pyqtSignal(float)   # 样品腔温度（D通道）
    sample_power_changed = pyqtSignal(float)   # 样品功率（0~100%）
    chamber_power_changed = pyqtSignal(float)   # 腔体功率（0~100%）
    error_occurred = pyqtSignal(str)           # 错误信息信号
    warning_occurred = pyqtSignal(str)         # 警告信息信号

    def _safe_emit(self, signal, *args):
        """统一发射信号的安全封装，避免在多个地方重复 try/except。
        信号发射失败时记录错误但不抛出。
        """
        try:
            signal.emit(*args)
        except Exception as e:
            try:
                name = getattr(signal, '__name__', str(signal))
            except Exception:
                name = str(signal)
            print(f"[MeasurementSystem] Failed to emit {name}: {e}")

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
        colors = ['#E6194B', '#3CB44B', '#4363D8', '#F58231']  # 红, 绿, 蓝, 橙
        for i, ch in enumerate(self.channels):
            self.channels[ch]['last_resistance'] = '--'
            self.channels[ch]['color'] = colors[i % len(colors)]

        self.save_path = base_dir
        self.lock = threading.Lock()

        # 先初始化硬件，若失败则捕获异常并发送错误信号
        while True:
            try:
                self.initialize_instruments()
            except Exception as e:
                error_msg = f"Failed to initialize instruments: {e}"
                print(error_msg)
                self._safe_emit(self.error_occurred, error_msg)
            else:
                break
            time.sleep(5)
            

        # 温度监控定时器 —— 仅在成功初始化硬件后启用

        self.temp_timer = QTimer()
        self.temp_timer.timeout.connect(self._update_hardware_temperatures_powers)
        self.temp_timer.start(200)  # 每200 ms更新一次硬件温度

        self.temp_display_timer = QTimer()
        self.temp_display_timer.timeout.connect(self._update_display_temperatures_powers)
        self.temp_display_timer.start(300)  # 每300 ms更新一次显示

    def get_available_sources(self):
        """返回已成功初始化的可用仪器列表。"""
        sources = []
        if self.k6221 is not None:
            sources.append("Keithley 6221")
        if self.tempcontroller is not None:
            sources.append("tempcontroller")
        if self.matrix is not None:
            sources.append("SwitchMatrix3706")
        return sources

    def initialize_instruments(self):
        try:
            print("Initializing instruments...")
            self.rm = pyvisa.ResourceManager()

            # 初始化各个仪器实例
            self.tempcontroller = KelvinionController(self.rm.open_resource(self.devices["kelvinion"]), self.pidramp)
            # 若需要使用 Model24CController，只需取消下面一行注释并注释上面一行
            # self.tempcontroller = Model24CController(self.rm.open_resource(self.devices["kelvinion"]), self.pidramp)"
            self.k6221 = Keithley6221(self.rm.open_resource(self.devices["k6221"]))
            self.matrix = SwitchMatrix3706(self.rm.open_resource(self.devices["matrix"]))

            print("All instruments initialized successfully.")
        except Exception as e:
            error_msg = f"Error initializing instruments: {e}"
            print(error_msg)
            self._safe_emit(self.error_occurred, error_msg)

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

    def _update_hardware_temperatures_powers(self):
        """
        定期从硬件获取温度数据并发送信号。
        这个方法由定时器每秒调用一次。
        """
        try:
            # 原子性一次性读取样品与腔体温度，避免交叉读写导致错位或交替值
            self.tempcontroller.temperatures = self.tempcontroller.read_temperatures()
            self.tempcontroller.powers = self.tempcontroller.read_powers()
        except Exception as e:
            error_msg = f"Failed to read temperatures from tempcontroller: {e}"
            print(f"[Temperature Update] {error_msg}")
            self._safe_emit(self.error_occurred, error_msg)
            if hasattr(self, 'tempcontroller') and self.tempcontroller is not None:
                self.tempcontroller.temperatures = (0.0, 0.0)
            else:
                # 创建轻量回退对象以供显示逻辑使用，避免 AttributeError
                self.tempcontroller = type('Dummy', (), {'temperatures': (0.0, 0.0), 'powers': (0.0, 0.0)})()

    def _update_display_temperatures_powers(self):
        # 发送温度信号
        if not hasattr(self, 'tempcontroller'):
            return
        try:
            sample_temp, chamber_temp = self.tempcontroller.temperatures
            self._safe_emit(self.sample_temp_changed, sample_temp)
            self._safe_emit(self.chamber_temp_changed, chamber_temp)
        except Exception as e:
            error_msg = f"Temperature display error: {e}"
            print(f"[Temperature Update] {error_msg}")
            self._safe_emit(self.error_occurred, error_msg)
            self._safe_emit(self.sample_temp_changed, 0.0)
            self._safe_emit(self.chamber_temp_changed, 0.0)
        
        # 发送功率信号
        try:
            sample_power, chamber_power = self.tempcontroller.powers
            self._safe_emit(self.sample_power_changed, sample_power)
            self._safe_emit(self.chamber_power_changed, chamber_power)
        except Exception as e:
            error_msg = f"Power read error: {e}"
            print(f"[Power Update] {error_msg}")
            self._safe_emit(self.sample_power_changed, 0.0)
            self._safe_emit(self.chamber_power_changed, 0.0)

    def measure_single_channel(self, ch_name, channel_config):
        attempts = 3
        backoff = 0.5
        try:
            current = float(channel_config['current'])
            Vrange = channel_config.get('voltage_range', '1V')
            pins = channel_config.get('pins', [])

            if not pins:
                print(f"Warning: No pins configured for channel {ch_name}. Skipping.")
                return float('nan')

            # 串行化整个测量过程，避免多个线程同时写入仪器导致超时
            with self.lock:
                # 1. 使用 connect 方法连接指定通道
                self.matrix.connect(pins)
                time.sleep(0.1)

                # 2. 重试 delta_measure 以应对偶发超时
                last_exc = None
                voltage = None
                for attempt in range(1, attempts + 1):
                    try:
                        voltage = self.k6221.measure_delta_mode(current, Vrange)
                        last_exc = None
                        break
                    except Exception as e:
                        last_exc = e
                        msg = str(e)
                        print(f"[System] delta_measure attempt {attempt} failed for {ch_name}: {msg}")
                        # 在超时或通信错误时，尝试发送中止并稍后重试
                        self.k6221.close()
                        time.sleep(backoff * attempt)

                if last_exc is not None and voltage is None:
                    # 最后一次仍失败，抛出异常以便上层处理
                    raise last_exc

                # 3. 计算电阻
                if abs(voltage) > 1e15:
                    resistance = float('inf')
                else:
                    resistance = voltage / current

                print(f"[System] Measured R = {resistance:.6e} Ohm for channel {ch_name} (V={voltage:.6e}, I={current:.2e})")
                return resistance

        except Exception as e:
            error_msg = f"Measurement error on channel {ch_name}: {e}"
            print(f"FATAL ERROR during measurement of channel {ch_name}: {e}")
            self._safe_emit(self.error_occurred, error_msg)
            # 如果 delta_measure 中途出错，尝试中止扫描
            try:
                self.k6221.close()
                print("[K6221] Sent ABORT command due to error.")
            except Exception as abort_e:
                print(f"Error sending ABORT command: {abort_e}")
            return float('nan')

        finally:
            # 无论成功与否，最后都断开所有开关 (重要安全步骤)
            self.matrix.open_all()


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

            # 如果已初始化 温控仪 实例，更新其 pidramp 引用
            if getattr(self, 'tempcontroller', None):
                self.tempcontroller.pidramp = data
            if not has_expected:
                # 发出警告信号，告知加载的文件可能不是完整的 pidramp 配置
                self._safe_emit(self.warning_occurred, 'Loaded PIDRAMP file missing some expected keys.')
            return True
        except Exception as e:
            # 转发错误到 UI
            self._safe_emit(self.error_occurred, f'Failed to load PIDRAMP: {e}')
            raise
