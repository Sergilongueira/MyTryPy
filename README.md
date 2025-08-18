# TENG Lab Data Acquisition and Processing

This repository contains scripts to acquire, merge, and load experimental data from the TENG laboratory.

## Data Acquisition

To obtain data from the TENG lab:

1. Run the script `MyGetData.py`.
2. In the pop-up window, click the **START LinMot** button.
3. Choose a folder on your computer where the data will be automatically saved.
4. When the experiment is finished, click **STOP LinMot**.
5. The data will then be automatically merged using the code in `MyMerger.py`.

## Loading and Processing Previously Generated Data

To load and process previously acquired and merged data:

1. Run the script `MyLoadData.py`.
2. In the pop-up window, select the folder containing the merged data.
3. The script will automatically look for the files `Motor_01.csv` and `DAQ_01.pkl` in the selected folder.
4. It will load these files, separate the data into cycles using the respective state variables, synchronize the datasets, and interpolate the file
   with fewer data points so that both datasets have the same length.
6. Finally, it will plot the position and voltage versus time.

The function `LoadFiles` in `MyLoadData.py` returns:

- `dfData_all`: a DataFrame containing all synchronized data from both files.
- A list of DataFrames `Cycles_list`, each corresponding to the data of an individual cycle.
