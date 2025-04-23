from launcher.services.runtime_downloader import get_available_runtimes, download_jre


x64 = get_available_runtimes().x64

download_jre(x64, "jre")
