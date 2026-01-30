import os
import json
from time import sleep
from random import randint
from datetime import datetime, timedelta
from pyautogui import alert
from pprint import pprint
from config.settings import logs_folder_path

def make_directories(paths: list[str]) -> None:
    for path in paths:
        path = os.path.expanduser(path)
        path = path.replace("//","/")
        if '.' in os.path.basename(path):
            path = os.path.dirname(path)
        if not path:
            continue
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
        except Exception as e:
            print(f'Error while creating directory "{path}": ', e)

def find_default_profile_directory() -> str | None:
    default_locations = [
        r"%LOCALAPPDATA%\Google\Chrome\User Data",
        r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data",
        r"%USERPROFILE%\Local Settings\Application Data\Google\Chrome\User Data"
    ]
    for location in default_locations:
        profile_dir = os.path.expandvars(location)
        if os.path.exists(profile_dir):
            return profile_dir
    return None

def critical_error_log(possible_reason: str, stack_trace: Exception) -> None:
    print_lg(possible_reason, stack_trace, datetime.now(), from_critical=True)

def get_log_path():
    try:
        path = logs_folder_path+"/log.txt"
        return path.replace("//","/")
    except Exception as e:
        critical_error_log("Failed getting log path! So assigning default logs path: './logs/log.txt'", e)
        return "logs/log.txt"

__logs_file_path = get_log_path()

def print_lg(*msgs: str | dict, end: str = "\n", pretty: bool = False, flush: bool = False, from_critical: bool = False) -> None:
    try:
        for message in msgs:
            pprint(message) if pretty else print(message, end=end, flush=flush)
            with open(__logs_file_path, 'a+', encoding="utf-8") as file:
                file.write(str(message) + end)
    except Exception as e:
        trail = f'Skipped saving this message: "{message}" to log.txt!' if from_critical else "We'll try one more time to log..."
        alert(f"log.txt in {logs_folder_path} is open or is occupied by another program! Please close it! {trail}", "Failed Logging")
        if not from_critical:
            critical_error_log("Log.txt is open or is occupied by another program!", e)

def buffer(speed: int=0) -> None:
    if speed<=0:
        return
    elif speed <= 1 and speed < 2:
        return sleep(randint(6,10)*0.1)
    elif speed <= 2 and speed < 3:
        return sleep(randint(10,18)*0.1)
    else:
        return sleep(randint(18,round(speed)*10)*0.1)

def manual_login_retry(is_logged_in: callable, limit: int = 2) -> None:
    count = 0
    while not is_logged_in():
        from pyautogui import alert
        print_lg("Seems like you're not logged in!")
        button = "Confirm Login"
        message = 'After you successfully Log In, please click "{}" button below.'.format(button)
        if count > limit:
            button = "Skip Confirmation"
            message = 'If you\'re seeing this message even after you logged in, Click "{}". Seems like auto login confirmation failed!'.format(button)
        count += 1
        if alert(message, "Login Required", button) and count > limit: return

def calculate_date_posted(time_string: str) -> datetime | None | ValueError:
    import re
    time_string = time_string.strip()
    now = datetime.now()
    match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago', time_string, re.IGNORECASE)
    if match:
        try:
            value = int(match.group(1))
            unit = match.group(2).lower()
            if 'second' in unit:
                return now - timedelta(seconds=value)
            elif 'minute' in unit:
                return now - timedelta(minutes=value)
            elif 'hour' in unit:
                return now - timedelta(hours=value)
            elif 'day' in unit:
                return now - timedelta(days=value)
            elif 'week' in unit:
                return now - timedelta(weeks=value)
            elif 'month' in unit:
                return now - timedelta(days=value * 30)
            elif 'year' in unit:
                return now - timedelta(days=value * 365)
        except (ValueError, IndexError):
            pass
    return None

def convert_to_lakhs(value: str) -> str:
    value = value.strip()
    l = len(value)
    if l > 0:
        if l > 5:
            value = value[:l-5] + "." + value[l-5:l-3]
        else:
            value = "0." + "0"*(5-l) + value[:2]
    return value

def convert_to_json(data) -> dict:
    try:
        result_json = json.loads(data)
        return result_json
    except json.JSONDecodeError:
        return {"error": "Unable to parse the response as JSON", "data": data}

def truncate_for_csv(data, max_length: int = 131000, suffix: str = "...[TRUNCATED]") -> str:
    try:
        str_data = str(data) if data is not None else ""
        if len(str_data) <= max_length:
            return str_data
        truncated = str_data[:max_length - len(suffix)] + suffix
        return truncated
    except Exception as e:
        return f"[ERROR CONVERTING DATA: {e}]"