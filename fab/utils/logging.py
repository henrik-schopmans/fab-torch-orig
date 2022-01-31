import abc
from typing import Any, Dict, List, Mapping, Union

import numpy as np
import wandb

LoggingData = Mapping[str, Any]


class Logger(abc.ABC):
    # copied from Acme: https://github.com/deepmind/acme
    """A logger has a `write` method."""

    @abc.abstractmethod
    def write(self, data: LoggingData) -> None:
        """Writes `data` to destination (file, terminal, database, etc)."""

    @abc.abstractmethod
    def close(self) -> None:
        """Closes the logger, not expecting any further write."""


class ListLogger(Logger):
    """Manually save the data to the class in a dict. Currently only supports scalar history
    inputs."""
    def __init__(self):
        self.history: Dict[str, List[Union[np.ndarray, float, int]]] = {}
        self.print_warning: bool = False

    def write(self, data: LoggingData) -> None:
        for key, value in data.items():
            if key in self.history:
                try:
                    value = float(value)
                except:
                    pass
                self.history[key].append(value)
            else:  # add key to history for the first time
                if isinstance(value, np.ndarray):
                    assert np.size(value) == 1
                    value = float(value)
                else:
                    if isinstance(value, float) or isinstance(value, int):
                        pass
                    else:
                        if not self.print_warning:
                            print("non numeric history values being saved")
                            self.print_warning = True
                self.history[key] = [value]

    def close(self) -> None:
        del self


class WandbLogger(Logger):
    def __init__(self, log_dir: str = "tmp", **kwargs: Any):
        self.run = wandb.init(dir=log_dir, **kwargs)  # type: ignore
        self._iter: int = 0

    def write(self, data: Dict[str, Any]) -> None:
        data = {f"{key}": metric for key, metric in data.items()}
        self.run.log(data, step=self._iter, commit=False)
        self._iter += 1

    def close(self) -> None:
        self.run.finish()

