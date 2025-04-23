import requests
from ..types import ProgressBar
from .console_progress import ConsoleProgresBar
import hashlib

def download(url: str, filename: str, sha1: str = None, size: int = 0, chunk_size: int = 2048, progressbar: ProgressBar = None):
    if progressbar is None:
        progressbar = ConsoleProgresBar(title=f"Downloading {filename}", total=size)

    use_sha1 = sha1 is not None

    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        if use_sha1:
            _hash = hashlib.sha1()
        with open(filename, "wb") as file:
            total = 0
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file.write(chunk)
                    total += len(chunk)
                    progressbar.update(total)
                    if use_sha1:
                        _hash.update(chunk)

        if use_sha1 and _hash.hexdigest() != sha1:
                raise ValueError(f"SHA1 hash mismatch: expected {sha1}, got {_hash.hexdigest()}")
