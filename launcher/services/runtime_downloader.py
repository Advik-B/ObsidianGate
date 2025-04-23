import os
import requests
from .downloader import download_file, uncompress_file, sha1_of_file
from ..types import JRE, MachineArch, JREAvailability, JREVersion, JREManifest
from typing import NamedTuple
import rich
from datetime import datetime

JRE_URL = "https://launchermeta.mojang.com/v1/products/launcher/a9ed4e847bec412e84bbdc95c11e7771218be683/windows-x86.json"

class Runtimes(NamedTuple):
    x64: JRE
    x86: JRE

def get_available_runtimes() -> Runtimes:
    manifest = requests.get(JRE_URL).json()

    def ret_JRE(m: list):
        m = m[0]
        return JRE(
            arch=MachineArch.X64,
            availability=JREAvailability(
                group=m["availability"]["group"],
                progress=m["availability"]["progress"]
            ),
            manifest=JREManifest(
                sha1=m["manifest"]["sha1"],
                size=m["manifest"]["size"],
                url=m["manifest"]["url"]
            ),
            version=JREVersion(
                name=m["version"]["name"],
                released=datetime.strptime(m["version"]["released"], "%Y-%m-%dT%H:%M:%S%z")
            )
        )

    return Runtimes(
        x64=ret_JRE(manifest["jre-x64"]),
        x86=ret_JRE(manifest["jre-x86"])
    )

def download_jre(jre: JRE, output_folder: str):
    os.makedirs(output_folder, exist_ok=True)
    m = requests.get(jre.manifest.url).json()["files"]
    for file in m:
        save_path = os.path.join(output_folder, file).replace("\\", "/")
        md = m[file]
        if md["type"] == "directory":
            os.makedirs(save_path, exist_ok=True)
            continue
        elif md["downloads"].get("lzma"):
            if os.path.exists(save_path):
                # rich.print(m)
                if sha1_of_file(save_path) == md["downloads"]["raw"]["sha1"]:
                    rich.print(f"[green]Skipping: [/] {save_path}")
                    continue

            save_path += ".lzma"
            download_file(
                url=md["downloads"]["lzma"]["url"],
                filename=save_path,
                size=md["downloads"]["lzma"]["size"]
            )
            assert sha1_of_file(save_path) == md["downloads"]["lzma"]["sha1"]
            uncompress_file(save_path, delete_after=True)
        else:
            if os.path.exists(save_path):
                if sha1_of_file(save_path) == md["downloads"]["raw"]["sha1"]:
                    rich.print(f"[green]Skipping: [/] {save_path}")
                    continue
            download_file(
                url=md["downloads"]["raw"]["url"],
                filename=save_path,
                size=md["downloads"]["raw"]["size"]
            )
            assert sha1_of_file(save_path) == md["downloads"]["raw"]["sha1"]
