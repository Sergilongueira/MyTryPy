import sys
import numpy as np
import pandas as pd
import time
from ctypes import byref, c_int32
from PyQt5.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer, pyqtSlot
import pyqtgraph as pg
from PyDAQmx import Task
from PyDAQmx.DAQmxConstants import *
from RaspberryInterface import RaspberryInterface
from MyMerger import Files_merge
import tkinter as tk
from tkinter import filedialog
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)


# %% ---------------- CONFIG ----------------
CHANNEL_LINMOT_ENABLE = "Dev1/ai0"
CHANNEL_LINMOT_UP_DOWN = "Dev1/ai1"
CHANNEL_TENG = "Dev1/ai2"

SAMPLE_RATE = 10000
SAMPLES_PER_CALLBACK = 100
CALLBACKS_PER_BUFFER = 500
BUFFER_SIZE = SAMPLES_PER_CALLBACK * CALLBACKS_PER_BUFFER

TimeWindowLength = 3  # seconds
PLOT_BUFFER_SIZE = ((SAMPLE_RATE * TimeWindowLength) // SAMPLES_PER_CALLBACK) * SAMPLES_PER_CALLBACK
refresh_rate = 10

moveLinMot = False


# %% ---------------- BUFFER PROCESSING THREAD ----------------
class BufferProcessor(QObject):
    process_buffer = pyqtSignal(object)

    def __init__(self, fs):
        super().__init__()
        self.fs = fs
        self.process_buffer.connect(self.save_data)
        self.timestamp = 0
        self.local_path = None

    @pyqtSlot(object)
    def save_data(self, data):
        if moveLinMot:
            t = np.arange(data.shape[0]) / self.fs + self.timestamp
            self.timestamp = t[-1] + (t[1] - t[0])
            df = pd.DataFrame({
                "Time (s)": t,
                "Signal": data[:, 2],
                "LINMOT_ENABLE": data[:, 0],
                "LINMOT_UP_DOWN": data[:, 1]
            })
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            df.to_pickle(f"{self.local_path}/DAQ_{timestamp}.pkl")
            logging.info(f"[+] Saved {len(data)} samples")


# %% ---------------- DAQ TASK WITH CALLBACK ----------------
class DAQTask(Task):
    def __init__(self, plot_buffer, processor_signal):
        super().__init__()

        self.plot_buffer = plot_buffer
        self.write_index = 0
        self.processor_signal = processor_signal

        self.buffer1 = np.empty((BUFFER_SIZE, 3))
        self.buffer2 = np.empty((BUFFER_SIZE, 3))
        self.current_buffer = self.buffer1
        self.index = 0

        self.CreateAIVoltageChan(f"{CHANNEL_LINMOT_ENABLE},{CHANNEL_LINMOT_UP_DOWN}", "", DAQmx_Val_RSE, -10.0, 10.0,
                                 DAQmx_Val_Volts, None)
        self.CreateAIVoltageChan(CHANNEL_TENG, "", DAQmx_Val_Diff, -10.0, 10.0, DAQmx_Val_Volts, None)
        self.CfgSampClkTiming("", SAMPLE_RATE, DAQmx_Val_Rising, DAQmx_Val_ContSamps, SAMPLES_PER_CALLBACK)
        self.AutoRegisterEveryNSamplesEvent(DAQmx_Val_Acquired_Into_Buffer, SAMPLES_PER_CALLBACK, 0)
        self.StartTask()

    def EveryNCallback(self):
        data = np.empty((SAMPLES_PER_CALLBACK, 3), dtype=np.float64)
        read = c_int32()
        self.ReadAnalogF64(SAMPLES_PER_CALLBACK, 10.0, DAQmx_Val_GroupByScanNumber, data, data.size, byref(read), None)

        # Threshold digital channels
        data[:, 0] = np.where(data[:, 0] < 2, 0, 1)
        data[:, 1] = np.where(data[:, 1] < 2, 0, 1)
        TENG_channel = data[:, 2]

        # Update circular plot buffer
        self.plot_buffer[self.write_index:self.write_index + SAMPLES_PER_CALLBACK] = TENG_channel
        self.write_index += SAMPLES_PER_CALLBACK
        if self.write_index == self.plot_buffer.size:
            self.write_index = 0

        # Save data to current buffer
        self.current_buffer[self.index:self.index + SAMPLES_PER_CALLBACK, :] = data
        self.index += SAMPLES_PER_CALLBACK

        if self.index >= BUFFER_SIZE:
            full_buffer = self.current_buffer
            self.current_buffer = self.buffer1 if self.current_buffer is self.buffer2 else self.buffer2
            self.index = 0
            self.processor_signal.emit(full_buffer)

        return 0


# %% ---------------- INTERFACE AND PLOT  ----------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DAQ Viewer")
        self.layout = QVBoxLayout(self)

        self.plot_buffer = np.zeros(PLOT_BUFFER_SIZE, dtype=float)

        self.plot_widget = pg.PlotWidget()
        self.curve = self.plot_widget.plot(self.plot_buffer, pen='y')

        hostname = "192.168.100.200"
        port = 22
        username = "TENG"
        password = "raspberry"
        self.remote_path = "/var/opt/codesys/PlcLogic/FTP_Folder"

        self.raspberry = RaspberryInterface(hostname=hostname, port=port, username=username, password=password)
        self.thread_raspberry = QThread()
        self.raspberry.moveToThread(self.thread_raspberry)
        self.thread_raspberry.start()
        self.raspberry.execute.emit(lambda: self.raspberry.connect())

        self.button = QPushButton("START LinMot")
        self.button.clicked.connect(self.toggle_linmot)
        self.layout.addWidget(self.button)
        self.layout.addWidget(self.plot_widget)

        self.processor = BufferProcessor(SAMPLE_RATE)
        self.thread = QThread()
        self.processor.moveToThread(self.thread)
        self.thread.start()

        self.task = DAQTask(self.plot_buffer, self.processor.process_buffer)

        self.DO_task_LinMotTrigger = DigitalOutputTask(line="Dev1/port0/line7")
        self.DO_task_LinMotTrigger.StartTask()

        self.DO_task_PrepareRaspberry = DigitalOutputTask(line="Dev1/port0/line6")
        self.DO_task_PrepareRaspberry.StartTask()

        self.DI_task_Raspberry_status_0 = DigitalInputTask(line="Dev1/port1/line0")
        self.DI_task_Raspberry_status_0.StartTask()

        self.DI_task_Raspberry_status_1 = DigitalInputTask(line="Dev1/port1/line1")
        self.DI_task_Raspberry_status_1.StartTask()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(refresh_rate)

    def update_plot(self):
        display_data = np.concatenate((
            self.plot_buffer[self.task.write_index:],
            self.plot_buffer[:self.task.write_index]
        ))
        self.curve.setData(display_data)

    def closeEvent(self, event):
        self.task.StopTask()
        self.task.ClearTask()

        self.DO_task_LinMotTrigger.set_line(0)
        self.DO_task_LinMotTrigger.StopTask()
        self.DO_task_LinMotTrigger.ClearTask()

        self.DO_task_PrepareRaspberry.set_line(0)
        self.DO_task_PrepareRaspberry.StopTask()
        self.DO_task_PrepareRaspberry.ClearTask()

        self.DI_task_Raspberry_status_0.StopTask()
        self.DI_task_Raspberry_status_0.ClearTask()

        self.DI_task_Raspberry_status_1.StopTask()
        self.DI_task_Raspberry_status_1.ClearTask()

        self.thread.quit()
        self.thread.wait()
        event.accept()

    def toggle_linmot(self):
        global moveLinMot

        if moveLinMot:
            self.DO_task_LinMotTrigger.set_line(0)
            self.DO_task_PrepareRaspberry.set_line(0)

            if self.task.index != 0:
                data = self.task.current_buffer[:self.task.index]
                self.task.processor_signal.emit(data)
                self.task.index = 0

            loop_counter = 0
            while loop_counter < 10000:
                status_bit_0 = self.DI_task_Raspberry_status_0.read_line()
                status_bit_1 = self.DI_task_Raspberry_status_1.read_line()
                if status_bit_0 == 0 and status_bit_1 == 0:
                    break
                loop_counter += 1

            if loop_counter >= 10000:
                logging.info("\033[91mError loop counter overflow, raspberry is not responding\033[0m")
                return

            self.raspberry.execute.emit(lambda: self.raspberry.download_folder(self.remote_path, local_path=self.processor.local_path))
            self.raspberry.execute.emit(lambda: self.raspberry.remove_files_with_extension(self.remote_path))

            time.sleep(1)
            if self.processor.local_path:
                Files_merge(folder_path=self.processor.local_path, save_path_folder=self.processor.local_path)

        else:
            logging.info("Please provide a save location for incoming data.")
            root = tk.Tk()
            root.withdraw()
            root.lift()
            root.attributes('-topmost', True)

            self.processor.local_path = filedialog.askdirectory()
            self.processor.timestamp = 0

            if not self.processor.local_path:
                logging.info("Canceled.")
                return

            self.processor.local_path = self.processor.local_path.replace("/", "\\")

            self.DO_task_PrepareRaspberry.set_line(1)

            loop_counter = 0
            while loop_counter < 10000:
                status_bit_0 = self.DI_task_Raspberry_status_0.read_line()
                status_bit_1 = self.DI_task_Raspberry_status_1.read_line()

                if status_bit_0 == 0 and status_bit_1 == 0:
                    loop_counter += 1
                elif status_bit_0 == 1 and status_bit_1 == 0:
                    break
                elif status_bit_0 == 0 and status_bit_1 == 1:
                    self.DO_task_PrepareRaspberry.set_line(0)
                    self.raspberry.execute.emit(lambda: self.raspberry.reset_codesys())
                    logging.info("\033[91mError, impossible to prepare raspberry to record, check codesys invalid license error. Resetting Codesys, please wait... \033[0m")
                    return
                else:
                    self.DO_task_PrepareRaspberry.set_line(0)
                    self.raspberry.execute.emit(lambda: self.raspberry.reset_codesys())
                    logging.info("\033[91mError, EtherCAT bus is not working, resetting Codesys, please wait...\033[0m")
                    return

            if loop_counter >= 10000:
                self.DO_task_PrepareRaspberry.set_line(0)
                logging.info("\033[91mError loop counter overflow, raspberry is not responding\033[0m")
                return

            self.task.index = 0
            self.DO_task_LinMotTrigger.set_line(1)

        moveLinMot = not moveLinMot
        self.button.setText("STOP LinMot" if moveLinMot else "START LinMot")


# %% ---------------- DIGITAL IO TASKS ----------------
class DigitalOutputTask(Task):
    def __init__(self, line="Dev1/port0/line7"):
        super().__init__()
        self.CreateDOChan(line, "", DAQmx_Val_ChanForAllLines)
        self.set_line(0)

    def set_line(self, value):
        data = np.array([value], dtype=np.uint8)
        self.WriteDigitalLines(1, 1, 10.0, DAQmx_Val_GroupByChannel, data, None, None)

class DigitalInputTask(Task):
    def __init__(self, line="Dev1/port1/line0"):
        super().__init__()
        self.CreateDIChan(line, "", DAQmx_Val_ChanForAllLines)

    def read_line(self):
        data = np.zeros(1, dtype=np.uint8)
        read = c_int32()
        self.ReadDigitalLines(1, 10.0, 0, data, 1, read, None, None)
        return data[0]


# %% ---------------- MAIN ----------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
