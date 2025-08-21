import pandas as pd
import os
import re
import tkinter as tk
from tkinter import filedialog

def LTIME_to_seconds(LTIME):
    
    conversor = {"h": 3600,
                 "m": 60,
                 "s": 1,
                 "ms": 1e-3,
                 "us": 1e-6,
                 "ns": 1e-9}

    units = re.split(r'\d+', LTIME)[1:]
    numbers_str = re.findall(r'\d+', LTIME)
    numbers = [int(number) for number in numbers_str]
    
    total_time = 0

    for number, unit in zip(numbers, units):
        total_time += number * conversor[unit]
    
    return total_time


def sort_function(string):
    return int(string.split("_")[-1].split(".")[0])


def CSV_merge(folder_path: str, save_path_folder: str, filename: str):
    files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]

    if not files:
        return
    
    if filename + '.csv' in files:
        files.remove(filename + '.csv')

    files.sort(key=sort_function)

    # Create an empty DataFrame
    combined_DataFrame = pd.DataFrame()

    # Iterate the CSV files found in the folder path
    print("\nMerging...")
    for file in files:
        # Read CSV
        df = pd.read_csv(os.path.join(folder_path, file), header=0, 
                         index_col=False, delimiter=';', decimal='.')

        print(file)

        # Concatenate CSV file
        combined_DataFrame = pd.concat([combined_DataFrame, df], ignore_index=True)
    
    combined_DataFrame['Time(s)'] = combined_DataFrame['Time(s)'].apply(LTIME_to_seconds)
    combined_DataFrame['Time(s)'] = combined_DataFrame['Time(s)'] - combined_DataFrame['Time(s)'].iloc[0]
    
    # Save concatenated DataFrame
    combined_DataFrame.to_csv(os.path.join(save_path_folder, filename + ".csv"), index=False)
    
    print("Data saved to location:", os.path.join(save_path_folder, filename + ".csv"))

    return


def Pickle_merge(folder_path: str, save_path_folder: str, filename: str):
    files = [f for f in os.listdir(folder_path) if f.endswith('.pkl')]

    if not files:
        return
    
    if filename + '.pkl' in files:
        files.remove(filename + '.pkl')
    
    files.sort(key=sort_function)

    # Create an empty DataFrame
    combined_DataFrame = pd.DataFrame()

    # Iterate the Excel files found in the folder path
    print("\nMerging...")
    for file in files:
        # Read Excel
        df = pd.read_pickle(os.path.join(folder_path, file))

        print(file)

        # Concatenate CSV file
        combined_DataFrame = pd.concat([combined_DataFrame, df], ignore_index=True)
    
    combined_DataFrame['Time (s)'] = combined_DataFrame['Time (s)'] - combined_DataFrame['Time (s)'].iloc[0]
    
    # Save concatenated DataFrame
    combined_DataFrame.to_pickle(os.path.join(save_path_folder, filename + ".pkl"))
    
    print("Data saved to location:", os.path.join(save_path_folder, filename + ".pkl"))

    return


def Files_merge(folder_path:str, save_path_folder:str):
    CSV_merge(folder_path, save_path_folder, filename='Motor_01')
    Pickle_merge(folder_path, save_path_folder, filename='DAQ_01')


if __name__ == "__main__":
    # Get file save location from user:
    print("Please provide a save location for incoming data.")
    root = tk.Tk()
    root.withdraw()  # Amaga la finestra princial de tkinter
    root.lift()  # Posa la finestra emergent en primer pla
    root.attributes('-topmost', True)  # La finestra sempre al davant

    # Carpeta con la lista de archivos CSV y Excel a combinar
    carpeta = filedialog.askdirectory()

    if carpeta:
        carpeta = carpeta.replace("/", "\\")

        CSV_merge(folder_path=carpeta, save_path_folder=carpeta, filename="Motor_01")
        Pickle_merge(folder_path=carpeta, save_path_folder=carpeta, filename="DAQ_01")

    else:
        print("Canceled.")