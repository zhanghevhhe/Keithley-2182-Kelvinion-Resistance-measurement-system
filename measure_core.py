import os
import json
import threading
import time
import pyvisa
from pyvisa.constants import StopBits
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

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
        self.pidramp = pidramp_config  # 存储配置
        self._lock = threading.Lock()  # 序列化对仪器的所有访问（读写）

        # 串口基础设置
        self.inst.baud_rate = 115200
        self.inst.data_bits = 8
        self.inst.stop_bits = StopBits.one
        self.temperatures = (0.0, 0.0)  # (sample_temp, chamber_temp)

        # 尝试安全查询 IDN，若失败则继续让上层处理异常
        try:
            print(self._safe_query('*IDN?'))
        except Exception:
            pass

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
                if entry["min"] <= target < entry["max"]:
                    ramp = entry["ramp"]
                    break
        self._safe_write(f"[SET:RAMP:A:{ramp}]")
        print(f"[Kelvinion] Set sample RAMP: {ramp}" + (f" (override: {ramp_override})" if ramp_override is not None else ""))

    def set_chamber_ramp(self, target: float, ramp_override: float = None):
        """
        同上，针对 chamber (loop B)。
        """
        if ramp_override is not None:
            ramp = ramp_override
        else:
            ramp = 1
            for entry in self.pidramp["chamber_ramp"]:
                if entry["min"] <= target < entry["max"]:
                    ramp = entry["ramp"]
                    break
        self._safe_write(f"[SET:RAMP:B:{ramp}]")
        print(f"[Kelvinion] Set chamber RAMP: {ramp}")

    def set_sample_pid(self, target: float):
        for entry in self.pidramp["sample_pid"]:
            if entry["min"] <= target < entry["max"]:
                # PID 写入在同一锁区域内进行，避免并发干扰
                with self._lock:
                    self.inst.write(f"[SET:PID:A:KP:{entry['P']}]")
                    time.sleep(0.1)
                    self.inst.write(f"[SET:PID:A:KI:{entry['I']}]")
                    # time.sleep(0.1)
                    #self.inst.write(f"[SET:PID:A:KD:0]")
                print(f"[Kelvinion] Set sample PID: P={entry['P']}, I={entry['I']}")
                break

    def set_chamber_pid(self, target: float):
        for entry in self.pidramp["chamber_pid"]:
            if entry["min"] <= target < entry["max"]:
                with self._lock:
                    self.inst.write(f"[SET:PID:B:KP:{entry['P']}]")
                    time.sleep(0.1)
                    self.inst.write(f"[SET:PID:B:KI:{entry['I']}]")
                    # time.sleep(0.1)
                    #self.inst.write(f"[SET:PID:B:KD:0]")
                print(f"[Kelvinion] Set chamber PID: P={entry['P']}, I={entry['I']}")
                break

    def set_sample_temperature(self, target: float):
        self._safe_write(f"[SET:SETP:A:{target}K]")
        print(f"[Kelvinion] Set sample temperature: {target}")

    def set_chamber_temperature(self, target: float):
        self._safe_write(f"[SET:SETP:B:{target}K]")
        print(f"[Kelvinion] Set sample temperature: {target}")

    def set_sample_range(self, target: float):
        
        for entry in self.pidramp["sample_range"]:
            if entry["min"] <= target < entry["max"]:
                self._safe_write(f"[SET:RANGE:A:{entry['range']}]")
                print(f"[Kelvinion] Set sample range: {entry['range']}")
                break

    def set_chamber_range(self, target: float):
        
        for entry in self.pidramp["chamber_range"]:
            if entry["min"] <= target < entry["max"]:
                self._safe_write(f"[SET:RANGE:B:{entry['range']}]")
                print(f"[Kelvinion] Set chamber range: {entry['range']}")
                break

    def set_temperature(self, target: float, loop: str = 'A', ramp_override: float = None):
        """
        增加 ramp_override：当 UI 手动设置温度时可传入临时速率覆盖 pidramp 表。
        """
        if loop == 'A':
            self.set_sample_temperature(target)
            self.set_sample_ramp(target, ramp_override)
            self.set_sample_pid(target)
            self.set_sample_range(target)
        elif loop == 'B':
            self.set_chamber_temperature(target)
            self.set_chamber_ramp(target, ramp_override)
            self.set_chamber_pid(target)
            self.set_chamber_range(target)
        print(f"[Kelvinion] Set loop {loop} to {target:.2f} K")

    def get_set_temperature(self, channel: str = 'A') -> float:  # A\B
        raw = self._safe_query(f"[READ:SETP:{channel}]")
        return float(raw[1:-3])

    def get_sample_temperature(self):
        """从属性获取样品温度（F通道，temperature第一个元素）"""
        return self.temperatures[0]
    
    def get_chamber_temperature(self):
        """从属性获取样品腔温度（D通道，temperature第二个元素）"""
        return self.temperatures[1]
    
    def get_temperatures(self):
        """
        原子性获取样品(F)和腔体(D)温度，返回 (sample_temp, chamber_temp)。
        UI / 外部调用应优先使用此接口避免并发交错。
        """
        with self._lock:
            raw_f = self.inst.query(f"[READ:K:F]")
            t_f = float(raw_f[1:-3])

            raw_d = self.inst.query(f"[READ:K:D]")
            t_d = float(raw_d[1:-3])
        return t_f, t_d
    
    def _tolerance(self, target: float) -> float:
        for entry in self.pidramp["tolerance_ranges"]:
            if entry["min"] <= target < entry["max"]:
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
            # 从属性获取温度，避免交叉读写
            t = self.get_sample_temperature() if loop == 'A' else self.get_chamber_temperature()
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
            t = self.get_sample_temperature() if loop == 'A' else self.get_chamber_temperature()
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
        self._send_2182("VOLT:CHAN1:DFIL:STAT ON")     # 开启数字滤波
        self._send_2182(f"VOLT:CHAN1:DFIL:COUN {count}")
        self._send_2182(f"VOLT:CHAN1:DFIL:WIND {window}")
        self._send_2182(f"VOLT:CHAN1:DFIL:TCON {filter_type}")
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

    def measure_dc_current(self, current, compliance=25, nplc=5, delay_s=1.2):
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
        self._send_2182("VOLT:RANG:AUTO ON")
        self._send_2182(f"VOLT:NPLC {nplc}")
        self.configure_2182_filter(count=5, window=0.01)

        # 配置 6221 (源)
        self.inst.write(f'CURR:COMP {compliance}')
        self.inst.write(':SOUR:CURR:RANG:AUTO ON')
        
        # 设置电流和源延时（等待稳定时间）
        self.inst.write(f':SOUR:CURR {current:.3e}')
        self.inst.write(f'SOUR:DEL {delay_s}') 
        
        # 2. 设置单点触发并打开输出
        self.inst.write('TRIG:COUN 1') # 只触发一次测量
        self.inst.write('TRIG:SOUR IMM') # 立即触发 (等待源稳定后即触发)
        self.inst.write('OUTP ON') # 打开电流输出
        
        # 3. 发起测量并等待完成
        # INIT 命令等待 SOUR:DEL 完成后，驱动 2182 完成一次读数，然后阻塞。
        print(f"[DC - Reliable] Initiating measurement I={current:.3e} A...")
        self.inst.write('INIT')
        
        # *OPC? 确保 INITIATE 序列（源稳定+测量）完全完成。
        self.inst.query('*OPC?') 
        
        try:
            # 4. 获取最新的、已完成的测量结果
            # 这里强制使用 'FETCH' 模式
            voltage = self.get_reading(mode='FETCH')
            
            print(f"[DC - Reliable] Measurement complete. V={voltage:.6e} V")
            return voltage
        except Exception as e:
            print(f"Error during DC measurement fetch: {e}")
            raise
        finally:
            # 单点测量完成后，关闭输出是安全惯例
            self.inst.write('OUTP OFF') 

    def measure_delta_mode(self, current, voltage_range=0.01, compliance=10, duration=5.0):
        """
        执行 Delta 模式测量 (正负电流交替消除热电势)
        
        *** 优化：TRAC:CLE 确保平均值基于本次测量 ***
        
        :param current: 电流幅值 (Amp)
        :param voltage_range: 2182 电压量程 (可以是字符串 '10mV' 或 浮点数 0.01)
        :param compliance: 顺从电压
        :param duration: 测量持续时间 (秒)
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
        self.inst.write('SENS:AVER:COUN 6')
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
        self.temp_timer.timeout.connect(self._update_hardware_temperatures)
        self.temp_timer.start(200)  # 每200 ms更新一次硬件温度

        self.temp_display_timer = QTimer()
        self.temp_display_timer.timeout.connect(self._update_display_temperatures)
        self.temp_display_timer.start(1000)  # 每秒更新一次显示

    def get_available_sources(self):
        """返回已成功初始化的可用仪器列表。"""
        sources = []
        if self.k6221 is not None:
            sources.append("Keithley 6221")
        if self.kelvinion is not None:
            sources.append("Kelvinion")
        if self.matrix is not None:
            sources.append("SwitchMatrix3706")
        return sources

    def initialize_instruments(self):
        try:
            print("Initializing instruments...")
            self.rm = pyvisa.ResourceManager()

            # 初始化各个仪器实例
            self.kelvinion = KelvinionController(self.rm.open_resource(self.devices["kelvinion"]),self.pidramp)
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



    def _update_hardware_temperatures(self):
        """
        定期从硬件获取温度数据并发送信号。
        这个方法由定时器每秒调用一次。
        """
        try:
            # 原子性一次性读取样品与腔体温度，避免交叉读写导致错位或交替值
            self.kelvinion.temperatures = self.kelvinion.get_temperatures()
        except Exception as e:
            error_msg = f"Failed to read temperatures from Kelvinion: {e}"
            print(f"[Temperature Update] {error_msg}")
            self._safe_emit(self.error_occurred, error_msg)
            self.kelvinion.temperatures = 0.0, 0.0

    def _update_display_temperatures(self):
        # 发送温度信号
        sample_temp, chamber_temp = self.kelvinion.temperatures
        try:
            self._safe_emit(self.sample_temp_changed, sample_temp)
            self._safe_emit(self.chamber_temp_changed, chamber_temp)
        except Exception as e:
            error_msg = f"Temperature display error: {e}"
            print(f"[Temperature Update] {error_msg}")
            self._safe_emit(self.error_occurred, error_msg)
            self._safe_emit(self.sample_temp_changed, 0.0)
            self._safe_emit(self.chamber_temp_changed, 0.0)

    def measure_single_channel(self, ch_name, channel_config):
        # --- 使用你提供的 delta_measure 方法进行真实测量 ---
        # 为避免多个并发测量导致仪器通信冲突和超时，使用系统级锁序列化对 matrix/k6221 的访问。
        # 同时在 delta_measure 出现超时的情况下进行有限次数的重试。
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
                        self.k6221.inst.write('SOURCE:SWEEP:ABORT')
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
                self.k6221.inst.write('SOURCE:SWEEP:ABORT')
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

            # 如果已初始化 kelvinion 实例，更新其 pidramp 引用
            if getattr(self, 'kelvinion', None):
                self.kelvinion.pidramp = data
            if not has_expected:
                # 发出警告信号，告知加载的文件可能不是完整的 pidramp 配置
                self._safe_emit(self.warning_occurred, 'Loaded PIDRAMP file missing some expected keys.')
            return True
        except Exception as e:
            # 转发错误到 UI
            self._safe_emit(self.error_occurred, f'Failed to load PIDRAMP: {e}')
            raise
