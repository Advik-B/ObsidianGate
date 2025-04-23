from rich.console import Console
from rich.text import Text
from rich.progress_bar import ProgressBar as RichProgressBar
from ..types import ProgressBar

class ConsoleProgresBar(ProgressBar):
    """
    A class that represents a console progress bar using the rich library.
    """

    def __init__(self, title: str, total: int):
        super().__init__(total=total)
        self.progress = RichProgressBar(total=total)

    def update(self, completed: int):
        """
        Update the progress bar with the number of completed tasks.
        """
        self.progress.update(completed)

    def setTotal(self, total: int):
        """
        Set the total number of tasks.
        """
        self.progress.total = total

    def setValue(self, value: int):
        """
        Set the current value of the progress bar.
        """
        self.progress.completed = value

    def getProgress(self) -> float:
        """
        Get the current progress as a percentage.
        """
        return self.progress.percentage_completed

    def setUnknown(self):
        """
        Set the progress bar to an unknown state.
        """
        self.progress.total = None

    def setKnown(self):
        """
        Set the progress bar to a known state.
        """
        self.progress.total = self.total