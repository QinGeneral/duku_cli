import time


def duration_to_string(duration):
    """
    Convert a duration given in seconds to a string in the format HH:MM:SS.

    Parameters
    ----------
    duration : int
        The duration in seconds.

    Returns
    -------
    str
        The duration in the format HH:MM:SS.
    """
    duration = int(duration)
    hour = duration // 3600
    minute = (duration % 3600) // 60
    second = duration % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def timestamp_to_time(timestamp):
    time_array = time.localtime(timestamp)
    return time.strftime("%Y-%m-%d", time_array)


def read_binary_from_file(file_name):
    f = open(file_name, "rb")
    return f.read()


def write_binary_to_file(file_name, content):
    with open(file_name, "wb") as binary_file:
        binary_file.write(content)


def read_from_file(file_name):
    """Read the content of a file."""
    with open(file_name, "r", encoding="utf-8") as file:
        return file.read()


def save_to_file(file_name, content):
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(content)

