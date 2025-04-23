from tqdm import tqdm
from ..types import ProgressBar

class ConsoleProgresBar(ProgressBar):
    """
    A class that represents a console progress bar using the tqdm library.
    """

    def __init__(self, title: str, total: int):
        super().__init__(total=total, title=title)
        self.pbar = tqdm(total=total, desc=title, unit='')
        self._value = 0  # To track current progress for setValue

    def update(self, completed: int):
        """
        Update the progress bar by advancing the given number of completed tasks.
        """
        self.pbar.update(completed)
        self._value += completed

    def setTotal(self, total: int):
        """
        Set the total number of tasks.
        """
        self.pbar.total = total
        self.pbar.refresh()

    def setValue(self, value: int):
        """
        Set the current value of the progress bar.
        """
        delta = value - self._value
        self.update(delta)

    def getProgress(self) -> float:
        """
        Get the current progress as a percentage.
        """
        if self.pbar.total:
            return (self._value / self.pbar.total) * 100
        return 0.0

    def setUnknown(self):
        """
        Set the progress bar to an unknown state (indeterminate).
        tqdm doesn't support this directly, but we can simulate it.
        """
        self.pbar.total = None
        self.pbar.refresh()

    def setKnown(self):
        """
        Reset the progress bar to a known total.
        """
        self.setTotal(self.total)

    def stop(self):
        """
        Close the progress bar.
        """
        self.pbar.close()
