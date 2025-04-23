from abc import ABC, abstractmethod
from typing import Union

# Abstract class for progress bar
class ProgressBar(ABC):
    """
    Abstract class for a progress bar.
    """
    def __init__(self, title: str, total: Union[int, float] = 0):
        """
        Initialize the progress bar with an optional total value.
        """
        self.value = 0
        self.total = total
        self.known = True
        self.title = title

    @abstractmethod
    def setUnknown(self):
        self.known = False

    @abstractmethod
    def setKnown(self):
        self.known = True

    @abstractmethod
    def setTotal(self, total: Union[int, float]):
        """
        Set the total number of items to process.
        """
        pass

    @abstractmethod
    def setValue(self, value: Union[int, float]):
        pass

    @abstractmethod
    def update(self, value: Union[int, float]):
        """
        Update the progress bar with the current value.
        """
        pass

    def getProgress(self) -> float:
        """
        Get the current progress as a percentage.
        """
        return (self.value / self.total) * 100 if self.total else 0


    def __enter__(self):
        """
        Enter the context manager.
        """
        return self