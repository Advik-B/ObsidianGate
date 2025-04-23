import lzma
from datetime import datetime

import requests
from .downloader import download
# import json
from ..types import JRE, MachineArch, JREAvailability, JREVersion, JREManifest
from typing import NamedTuple
import rich

JRE_URL = "https://launchermeta.mojang.com/v1/products/launcher/a9ed4e847bec412e84bbdc95c11e7771218be683/windows-x86.json"

class Runtimes(NamedTuple):
    x64: JRE
    x86: JRE

def get_available_runtimes() -> Runtimes:
    manifest = requests.get(JRE_URL).json()


    def ret_JRE(m: dict):
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
                # 2018-09-21T11:55:01+00:00
                released=datetime.strptime(m["version"]["released"], "%Y-%m-%dT%H:%M:%S%z")
            )
        )

    return Runtimes(
        x64=ret_JRE(manifest["jre-x64"]),
        x86=ret_JRE(manifest["jre-x86"])
    )
