import numpy as np
import pandas as pd
import os
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from scipy.signal import peak_widths
from operator import concat
import seaborn as sns
import tkinter as tk
from tkinter import filedialog, simpledialog
from MyLoadData import LoadFiles

# %% INITIAL CONFIGURATION

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

REQ_LEVEL = 25
logging.addLevelName(REQ_LEVEL, "REQ")

def req(self, message, *args, **kwargs):
    if self.isEnabledFor(REQ_LEVEL):
        self._log(REQ_LEVEL, message, args, **kwargs)

logging.Logger.req = req
logger = logging.getLogger(__name__)


mpl.use('Qt5Agg')
plt.close('all')
plt.ion()


# %% DEFINITION OF FOLDER PATHS AND FILE NAMES TO USE

def Path_Selection():
    logger.req('Please provide a folder location.')
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes('-topmost', True)
    ExpsDir = filedialog.askdirectory('Select Experiments Directory')
    if ExpsDir:
        ExpsDir = os.path.normpath(ExpsDir)
    else:
        logging.info('File Selection Canceled.')
        return None, None, None
    
    RawDataDir = os.path.join(ExpsDir, 'RawData')
    ReportsDir = os.path.join(ExpsDir, 'Reports')
    DataSetsDir = os.path.join(ExpsDir, 'DataSets')
    
    logger.req('Please provide a file location.')
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes('-topmost', True)
    ExpsDef = filedialog.askdirectory('Select Experiments Desciption Excel File')
    if ExpsDef:
        ExpsDef = os.path.normpath(ExpsDef)
    else:
        logging.info('File Selection Canceled.')
        return None, None, None
    
    logger.req('Please provide a file location.')
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes('-topmost', True)
    LoadsDef = filedialog.askdirectory('Select Loads Desciption Excel File')
    if LoadsDef:
        LoadsDef = os.path.normpath(LoadsDef)
    else:
        logging.info('File Selection Canceled.')
        return None, None, None
    
    dfExps = pd.read_excel(ExpsDef)
    
    logger.req('Please select a TribuId value.')
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes(-'topmost', True)
    TribuId = simpledialog.askstring('TribuId Selection', 'Enter a valid TribuId value:')  # !!!
    if not TribuId:
        logger.info('Selection canceled by the user.')
        return None, None, None
    elif TribuId in dfExps['TribuId'].dropna().unique():
        logger.info(f'TribuId value correctly saved: {TribuId}')
        dfExps = dfExps[dfExps['TribuId'] == TribuId]
    else:
        logger.info(f'Invalid TribuId value: {TribuId}')
        return None, None, None
    
    dfLoads = pd.read_excel(LoadsDef)
    
    LoadsFields = ('Req', 'Gain', 'Ceq')
    for lf in LoadsFields:
        if lf not in dfExps.columns:
            dfExps.insert(2, lf, None)   
    for idx, r in dfExps.iterrows():
        if r.RloadId in dfLoads.RloadId.values:
            for lf in LoadFiles:
                dfExps.loc[idx, lf] = dfLoads.loc[dfLoads.RloadId == r.RloadId, lf].values[0]
        elif r.RloadId == 'ElectrodeImpedance':
            logging.warning(f'Load {r.RloadId} is Electrode Impedance. Assigned to 80 kOhms.')
            dfExps.loc[idx, 'Req'] = 80e3  # Ohms
            dfExps.loc[idx, 'Gain'] = 1
            dfExps.loc[idx, 'Ceq'] = float('inf')  # ???
        else:
            logging.warning(f'Load {r.RloadId} not found. Assigned open circuit.')
            dfExps.loc[idx, 'Req'] = float('inf')
            dfExps.loc[idx, 'Gain'] = 1
            dfExps.loc[idx, 'Ceq'] = float('inf')  # ???
     
        
    for idx, r in dfExps.iterrows():
        DaqFile = os.path.join(RawDataDir, r.DaqFile)
        if os.path.isfile(DaqFile):
            dfExps.loc[idx, 'DaqFile'] = DaqFile
        else:
            logging.warning(f'File {DaqFile} not found. Experiment {r.ExpId} dropped.')
            dfExps.drop(idx, inplace=True)
        
        MotorFile = os.path.join(RawDataDir, r.MotorFile)
        if os.path.isfile(MotorFile):
            dfExps.loc[idx, 'MotorFile'] = MotorFile
        else:
            logging.warning(f'File {MotorFile} not found. Experiment {r.ExpId} dropped.')
            dfExps.drop(idx, inplace=True)
    
    return dfExps, ReportsDir, DataSetsDir



dfExps, ReportsDir, DataSetsDir = Path_Selection()

if dfExps is not None:
    plt.ioff()
    exps_summary = []
    
    for exp_idx, r in dfExps.iterrows():
        logging.info(f'Processing: {r.ExpId}')
        dfData, Cycles_list = LoadFiles(r)

        if dfData.empty:
            logging.warning(f'Experiment {r.ExpId} dropped.')
            continue
        
        if np.all(dfData.Current is None):
            logging.warning("Current column not found in experiment %s. " 
                            "Cannot verify if Ohm's Law is satisfied.", r.ExpId)
        else:
            tolerance = 0.2  # 20% tolerance
            I_theo = dfData['Voltage'] / r.Req
            ratio = dfData['Current'] / I_theo
            if np.all(np.abs(ratio - 1) <= tolerance):
                logging.info("Experiment %s: Ohm's Law satisfied within %s%% tolerance.",
                             r.ExpId, int(tolerance * 100))
            else:
                logging.warning("Experiment %s: Ohm's Law NOT satisfied within %s%% tolerance.",
                                r.ExpId, int(tolerance * 100))
        
        exp_df = pd.DataFrame(columns=[
            'VoltageMax',
            'VoltageMin',
            'PosPeakWidth',
            'NegPeakWidth',
            'PosEnergy',
            'NegEnergy',
            'TotEnergy'
            ])
        
        for cy_idx, cy in Cycles_list:
            imax = cy.Voltage.idxmax()
            imin = cy.Voltage.idxmin()
            MaxPeakWidth = peak_widths(cy.Voltage, [imax], rel_height=0.5)
            MinPeakWidth = peak_widths(-cy.Voltage, [imin], rel_height=0.5)
            MaxPeakWidth = MaxPeakWidth[0] * cy.Time.diff().mean()
            MinPeakWidth = MinPeakWidth[0] * cy.Time.diff().mean()
            cy.Power = cy.Voltage**2 / r.Req
            
            exp_df.loc[cy_idx, 'VoltageMax'] = r.Voltage[imax]
            exp_df.loc[cy_idx, 'VoltageMin'] = r.Voltage[imin]
            exp_df.loc[cy_idx, 'PosPeakWidth'] = MaxPeakWidth
            exp_df.loc[cy_idx, 'NegPeakWidth'] = MinPeakWidth
            exp_df.loc[cy_idx, 'PosEnergy'] = None
            exp_df.loc[cy_idx, 'NegEnergy'] = None
            exp_df.loc[cy_idx, 'TotEnergy'] = exp_df.loc[cy_idx, 'PosEnergy'] + \
                                              exp_df.loc[cy_idx, 'NegEnergy']
            
        exp_dicc = {
            'exp_idx': exp_idx,
            'ExpId': r.ExpId,
            'TribuId': r.TribuId,
            'Date': r.Date,
            'Temperature': r.Temperature,
            'Humidity': r.Humidity,
            'Req': r.Req,
            'NumCycles': len(Cycles_list),
            'AvgVoltageMax': exp_df.VoltageMax.mean(),
            'AvgVoltageMin': exp_df.VoltageMin.mean(),
            'AvgPosPeakWidth': exp_df.PosPeakWidth.mean(),
            'AvgNegPeakWidth': exp_df.NegPeakWidth.mean(),
            'AvgTotalEnergy': exp_df.NegEnergy.mean(),
            'Duration': exp_df.Time.iloc[-1],
            'Valid': True,
            'Notes': None,
            'DataFrame': exp_df
            }
    
        exps_summary.append(exp_dicc)
    
    exps_summary = list(enumerate(exps_summary))
    
    
    























