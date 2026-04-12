import os
import random

import numpy as np
import torch


def seeding(seed: int) -> None:
    """Seed all sources of randomness for reproducibility."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True


def create_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)


def shuffling(x: list, y: list) -> tuple[list, list]:
    """Shuffle two parallel lists in unison with a fixed seed."""
    combined = list(zip(x, y))
    random.shuffle(combined)
    x_shuffled, y_shuffled = zip(*combined) if combined else ([], [])
    return list(x_shuffled), list(y_shuffled)


def epoch_time(start_time: float, end_time: float) -> tuple[int, int]:
    """Convert elapsed time to minutes and seconds."""
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs


def print_and_save(file_path: str, data_str: str) -> None:
    """Print a string and append it to a log file."""
    print(data_str)
    with open(file_path, "a") as file:
        file.write(data_str)
        file.write("\n")
