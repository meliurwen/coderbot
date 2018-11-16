"""
"""

from flask import jsonify
import json
from coderbot import CoderBot
from program import ProgramEngine, Program
from config import Config
import connexion
import time
import sqlite3

## Imports for experimental mode
from pathlib import Path
import signal
import os
import errno
from program_v2 import Program_v2

bot_config = Config.get()
bot = CoderBot.get_instance(
    servo=(bot_config.get("move_motor_mode") == "servo"),
    motor_trim_factor=float(bot_config.get("move_motor_trim", 1.0)),
)

prog = None
prog_engine = ProgramEngine.get_instance()


## Functions
# Status File
def read_statusFile(temp_files_dict):
    tmp_folder_path = temp_files_dict["tmp_folder_path"]
    status_fileName = temp_files_dict["status_fileName"]

    # Load the status file
    with open(tmp_folder_path + status_fileName, "r") as fh:
        try:
            data_coderbotStatus = json.loads(fh.read())
        except Exception as e:
            print("####### JSON ERROR: "+str(e))
            print("####### FILE: "+str(fh.read()))
            print("####### PATH: "+ tmp_folder_path + status_fileName)
            data_coderbotStatus = None
        return data_coderbotStatus


def write_statusFile(data_coderbotStatus, temp_files_dict):
    tmp_folder_path = temp_files_dict["tmp_folder_path"]
    status_fileName = temp_files_dict["status_fileName"]

    # Create the file and if already exists overwites it
    with open(tmp_folder_path + status_fileName + ".tmp", "w") as fh:
        fh.write(json.dumps(data_coderbotStatus))
        os.rename(tmp_folder_path + status_fileName + ".tmp", tmp_folder_path + status_fileName)


def write_prog_gen_commands(command, mode, temp_files_dict):
    tmp_folder_path = temp_files_dict["tmp_folder_path"]
    status_fileName = temp_files_dict["status_fileName"]
    prog_gen_commands_fileName = temp_files_dict["prog_gen_commands_fileName"]

    data_prog_gen_commands = {}
    data_prog_gen_commands["command"] = command
    data_prog_gen_commands["argument"] = mode
    # Create the file and if already exists overwites it
    with open(tmp_folder_path + prog_gen_commands_fileName + ".tmp", "w") as fh:
        fh.write(json.dumps(data_prog_gen_commands))
        os.rename(tmp_folder_path + prog_gen_commands_fileName + ".tmp", tmp_folder_path + prog_gen_commands_fileName)


# Initialize the status file
def initialize_coderbotStatus(temp_files_dict):
    tmp_folder_path = temp_files_dict["tmp_folder_path"]
    status_fileName = temp_files_dict["status_fileName"]
    # The try-except has been used in order to avoid race conditions between the evaulation
    # of the existence of the folder and its creation
    try:
        os.makedirs(tmp_folder_path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    # Initial JSON
    default_status = {"ok":True, "prog_gen":{}, "prog_handler":{"mode": "stop"}}
    write_statusFile(default_status, temp_files_dict)


# Initialize the status file
temp_files_dict = {"tmp_folder_path": "tmp/", "status_fileName": "coderbotStatus_temp.json", "prog_gen_commands_fileName": "coderbotProg_gen_commands_temp.json"}
initialize_coderbotStatus(temp_files_dict)



## API

def stop():
    bot.stop()
    return "ok"


def move(data):
    print(data)
    bot.move(speed=data["speed"], elapse=data["elapse"])
    return 200


def turn(data):
    print(data)
    bot.turn(speed=data["speed"], elapse=data["elapse"])
    return 200


def status():
    return {
    	"status": "ok", "internetConnectivity": True, "temp": "40", "uptime": "5h", "status": "ok", "internetConnectivity": True, "temp": "40", "uptime": "5h"}


# Hardware and software information
def info():
    return {
        "model": 1,
        "serial": 2,
        "cbVersion": 3,
        "backendVersion": 4,
        "vueVersion": 5,
        "kernel": 6,
    }


def list(data):
    return json.dumps(prog_engine.prog_list())


def exec(data):
    prog = prog_engine.create(data["name"], data["code"])
    return json.dumps(prog.execute())


def save(data):
    prog = Program(data["name"], data["code"], data["dom_code"])
    prog_engine.save(prog)
    return "ok"


def load(data):
    prog = prog_engine.load(data["id"])
    return jsonify(prog.as_json())


def delete(data):
    prog_engine.delete(data["name"])
    return "ok"


def editSettings(data):
    return "ok"

def restoreSettings():
    with open('defaultConfig.json') as f:
        Config.write(json.loads(f.read()))
    bot_config = Config.get()
    return "ok"

def exec_experimental(data):
    code = data["code"]
    mode = data["mode"]


    # Load the status file
    data_coderbotStatus = read_statusFile(temp_files_dict)

    # if read_statusFile(temp_files_dict) returns None type, a reboot is needed
    if data_coderbotStatus is None:
        return json.dumps({"ok":False, "error_code":"coderbotStatusJsonError"}), 500


    if data_coderbotStatus["prog_handler"]["mode"] != "stop":
        prog_gen_pid = int(data_coderbotStatus["prog_gen"]["pid"])
        try:
            os.kill(prog_gen_pid, 0)
        except OSError:
            prog_gen_is_up = False
        else:
            prog_gen_is_up = True
        if not prog_gen_is_up:
            data_coderbotStatus["prog_gen"] = {}
            data_coderbotStatus["prog_handler"]["mode"] = "stop"
            write_statusFile(data_coderbotStatus, temp_files_dict)

    if data_coderbotStatus["prog_handler"]["mode"] == "stop":
        data_coderbotStatus["prog_handler"]["mode"] = mode
        write_statusFile(data_coderbotStatus, temp_files_dict)
        evaulation = Program_v2.run(code, mode, temp_files_dict)
    else: # data_coderbotStatus["prog_handler"]["mode"] == "stepByStep" or "fullExec"
        if mode == "stop":
            signal_to_program = signal.SIGTERM
        else: #else mode == "fullExec" or mode == stepByStep"
            write_prog_gen_commands("change_mode", mode, temp_files_dict)
            signal_to_program = signal.SIGUSR1

        try:
            os.kill(prog_gen_pid, signal_to_program)
        except Exception as err:
            # The process in reality was already terminated, probably because of some crash or the previous program unexpectedly terminated after the "data_coderbotStatus" dict
            # has been retrieved from the file (this last case is really unlikely to happen).
            print("######### error: "+str(err))

        evaulation = {"ok":True,"description":""}

    # Returns a positive or error response
    if evaulation["ok"]:
        return json.dumps(evaulation), 200
    else:
        return json.dumps(evaulation), evaulation["error_code"]
