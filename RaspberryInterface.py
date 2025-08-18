import paramiko
import hashlib
import os
from pathlib import Path
import stat
import time
import tkinter as tk
from tkinter import filedialog
import logging

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

class RaspberryInterface(QObject):

    execute = pyqtSignal(object)

    def __init__(self, hostname, port, username, password, 
                 codesys_folder="/var/opt/codesys/PlcLogic/FTP_Folder"):

        super().__init__()
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.codesys_folder = codesys_folder
        self.current_path = str(Path("__file__").resolve().parent)
        self.execute.connect(self.run_function)
        
        # Create SSH client
        self.ssh = paramiko.SSHClient()
        
        # Automatically add unknown hosts
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    @pyqtSlot(object)
    def run_function(self, function):
        function()

    def shutdown(self):
        stdin, stdout, stderr = self.ssh.exec_command("sudo poweroff")
        
    def reboot(self):
        stdin, stdout, stderr = self.ssh.exec_command("sudo reboot")
    
    def stop_codesys(self):
        
        command = "sudo service codesyscontrol stop"
        stdin, stdout, stderr = self.ssh.exec_command(command)
        
        # Wait until command finishes
        stdout.channel.recv_exit_status()
        
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
        else:
            logging.info("codesyscontrol stopped")
        
    def start_codesys(self):
        
        command = "sudo service codesyscontrol start"
        stdin, stdout, stderr = self.ssh.exec_command(command)
        
        # Wait until command finishes
        stdout.channel.recv_exit_status()
        
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
        else:
            logging.info("codesyscontrol started")
            
    def reset_codesys(self):
        self.stop_codesys()
        self.start_codesys()
        logging.info("Codesys has been reset succesfully")
        
    def check_file_integrity(self, local_path, remote_path):
        
        # Important, els noms de fitxers han d'anar entre "" 
        # Les () en la terminal es consideren per fer subprocessos o arrays
        command = f"sha256sum '{remote_path}'"
        stdin, stdout, stderr = self.ssh.exec_command(command)
        
        # Wait until command finishes
        stdout.channel.recv_exit_status()
        
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
            
        sha256sum_remote = stdout.read().decode().split("  ")[0]
    
        with open(local_path, "rb") as file:
            data = file.read()
            sha256_local = hashlib.sha256(data).hexdigest()
        
        logging.info("Remote SHA256:", sha256sum_remote)
        logging.info("Local SHA256:", sha256_local)
        
        if sha256sum_remote == sha256_local:
            logging.info("File integrity success, hash match!")
            return True
        else:
            logging.info("File integrity failed, hash doesn't match")
            return False
        
    def upload_file(self, local_path, remote_path):
        
        logging.info(f"Uploading file from {local_path} to {remote_path}")
        
        # Loading into /tmp/ because sftp doesn't have sudo privilegies
        file_name = os.path.split(local_path)[-1]
        self.sftp.put(local_path, f"/tmp/{file_name}")
        
        # Move from /tmp/ to the remote_path using sudo
        command = f"sudo mv '/tmp/{file_name}' '{remote_path}'"
        stdin, stdout, stderr = self.ssh.exec_command(command)
        
        # Wait until command finishes
        stdout.channel.recv_exit_status()
        
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
            
        # Check file integrity
        if self.check_file_integrity(local_path, remote_path):
            logging.info("File Successfully uploaded")
            return True
        else:
            logging.info("Error when uploading the file")
            return False
            
    def download_file(self, remote_path, local_path, max_retries = 5):
        
        attempt = 0
        while attempt < max_retries:
            logging.info(f'\nDownloading file: {remote_path}')
            self.sftp.get(remote_path, local_path)
            
            # Check file integrity
            if self.check_file_integrity(local_path, remote_path):
                logging.info("File Successfully downloaded")
                return
            else:
                logging.info(f"Retrying in 1 second, attempt = {attempt}")
                attempt += 1
                time.sleep(1)
    
        raise Exception("Error while trying to download a file")
    
    def download_folder(self, remote_path, local_path=None):
        
        if local_path == None:
            # Get file save location from user:
            logging.info("Please provide a save location for incoming data.")
            root = tk.Tk()
            root.withdraw()  # Amaga la finestra princial de tkinter
            root.lift()   # Posa la finestra emergent en primer pla
            root.attributes('-topmost', True)  # La finestra sempre al davant
    
            local_path = filedialog.askdirectory()
    
            if local_path:
                local_path = local_path.replace("/", "\\")
            else:
                logging.info("Canceled.")
                return
            
        else:
            current_path = str(Path("__file__").resolve().parent)
            local_path = os.path.join(current_path, local_path)
    
        os.makedirs(local_path, exist_ok=True)  # Don't raise error if it exist
                
        for item in self.sftp.listdir_attr(remote_path):
            
            remote_item = remote_path + '/' + item.filename
            local_item = os.path.join(local_path, item.filename)
            
            if stat.S_ISDIR(item.st_mode):
                # If it is a folder, do recursive call
                self.download_folder(self.sftp, remote_item, local_item)
            else:
                # If it is a file, download it
                self.download_file(remote_item, local_item)
    
        logging.info("\nFolder successfully downloaded into the path: ", local_path)
        return local_path
    
    def remove_file(self, remote_path):
        
        command = f"sudo rm -v '{remote_path}'"
        stdin, stdout, stderr = self.ssh.exec_command(command)
        
        # Wait until command finishes
        stdout.channel.recv_exit_status()
        
        # Deleted file:
        deleted_file = stdout.read().decode()
        logging.info("File to remove:", deleted_file)
        
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
        else:
            logging.info("File successfully removed")
            
    def remove_folder(self, remote_path):
        
        command = f"sudo rm -rf -v '{remote_path}'"
        stdin, stdout, stderr = self.ssh.exec_command(command)
        
        # Wait until command finishes
        stdout.channel.recv_exit_status()
        
        # Deleted file:
        deleted_items = stdout.read().decode()
        logging.info("Folder and files to remove:")
        logging.info(deleted_items)
        
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
        else:
            logging.info("Files and folders successfully removed")
            
    def remove_files_with_extension(self, remote_folder_path, extension = ".csv"):
        command = f"sudo find {remote_folder_path} -type f -name '*{extension}' -logging.info -delete"
        stdin, stdout, stderr = self.ssh.exec_command(command)
    
        # Wait until command finishes
        stdout.channel.recv_exit_status()
    
        # Deleted files:
        deleted_files = stdout.read().decode()
        logging.info("Files to remove:")
        logging.info(deleted_files)
    
        # Check command error
        error = stderr.read().decode()
        if error != '':
            raise Exception(error)
        else:
            if deleted_files:
                logging.info("Files successfully removed")
            else:
                logging.info("There are no files to remove")
                
    def get_elements(self, folder_path):
        # Get elements from a path
        list_elements = self.sftp.listdir(folder_path)
        return list_elements
    
    def get_files(self, folder_path):
        # Obtenir nomes fitxers, excloure les carpetes
        entries = self.sftp.listdir_attr(folder_path)
        path_files = [e.filename for e in entries if stat.S_ISREG(e.st_mode)]
        return path_files
    
    def get_folders(self, folder_path):
        # Obtenir nomes carpetes
        entries = self.sftp.listdir_attr(folder_path)
        path_folders = [e.filename for e in entries if stat.S_ISDIR(e.st_mode)]
        return path_folders
    
    def connect(self):
        try:
            # Connect to the host
            logging.info("Connecting to raspberry...")
            self.ssh.connect(hostname=self.hostname,
                             port=self.port,
                             username=self.username,
                             password=self.password)
            logging.info("Connected Succesfully")
            
            # Iniciar sesión SFTP
            logging.info("Starting sFTP server...")
            self.sftp = self.ssh.open_sftp()
            logging.info("sFTP server started successfully")
    
        except paramiko.AuthenticationException:
            logging.info("Authentication failed.")
        except paramiko.SSHException as e:
            logging.info(f"SSH error: {e}")
        except Exception as e:
            logging.info(f"Other error: {e}")
    
    def disconnect(self):
        # Close the connection
        self.ssh.close()
        self.sftp.close()
        logging.info("Socket closed")
        
        
if __name__ == "__main__":
    
    hostname = "192.168.100.200"
    port = 22
    username = "TENG"
    password = "raspberry"

    remote_path = "/var/opt/codesys/PlcLogic/FTP_Folder"
    
    raspberry = RaspberryInterface(hostname = hostname,
                                   port = port,
                                   username = username,
                                   password = password)
    
    raspberry.connect()

    
    

