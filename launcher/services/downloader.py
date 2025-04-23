import hashlib
import lzma
import os
import requests
from rich.progress import Progress


def sha1_of_file(path: str) -> str:
    hasher = hashlib.sha1()
    with open(path, 'rb') as f:
        while True:
            data = f.read(8192)
            if not data:
                break
            hasher.update(data)
    return hasher.hexdigest()

def uncompress_file(path: str, delete_after: bool = False):
    save_path = path.removesuffix('.lzma')
    # Uncompress file in chunks to avoid memory issues
    with open(path, 'rb') as compressed_file:
        with lzma.open(compressed_file) as decompressor:
            with open(save_path, 'wb') as decompressed_file:
                while True:
                    data = decompressor.read(8192)
                    if not data:
                        break
                    decompressed_file.write(data)

    if delete_after:
        os.remove(path)

def download_file(url: str, filename: str, size: int):
        # Download the file
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Check if the file exists and its size
        if os.path.exists(filename) and os.path.getsize(filename) == size:
            print(f"File {filename} already exists and is of correct size.")
            return

        # Save the file with a progress bar
        with Progress() as progress:
            task = progress.add_task(f"Downloading {filename}", total=size)
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
