import os
import json
import platform
import subprocess
import hashlib
import zipfile
import shutil
import requests
import uuid
import time
import concurrent.futures # Import for threading
from concurrent.futures import ThreadPoolExecutor, as_completed # Specific imports
import threading # For potential locks if needed later

from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TextColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    SpinnerColumn,
    TaskID, # Import TaskID for type hinting
)
from rich.panel import Panel
from rich.rule import Rule
from rich.live import Live # To manage overall task description updates smoothly

# --- Configuration ---
MINECRAFT_DIR = os.path.join(os.getenv('APPDATA') or os.path.expanduser("~/.minecraft"), '.minecraft_py_launcher_rich_mt')
# MINECRAFT_DIR = '.minecraft_py_launcher_rich_mt'
VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
ASSET_BASE_URL = "https://resources.download.minecraft.net/"
OFFLINE_USERNAME = "Player"
TARGET_VERSION = "1.17.1"
JAVA_EXECUTABLE = "java"
MAX_DOWNLOAD_WORKERS = 16 # Number of threads for downloading tasks (libs/assets)
MAX_EXTRACT_WORKERS = max(1, os.cpu_count()) # Fewer workers for CPU/Disk bound extraction

# Initialize Rich Console
console = Console()

# --- Helper Functions ---

def get_sha1(filepath):
    """Calculate SHA1 hash of a file."""
    h = hashlib.sha1()
    try:
        with open(filepath, 'rb') as file:
            while True:
                chunk = file.read(8192) # Larger chunk size might be slightly faster
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None

# Modified download_file to be thread-friendly and return success status + path
def download_file(url: str, path: str, expected_sha1: str | None = None, retries: int = 3, progress: Progress | None = None, task_id: TaskID | None = None) -> tuple[bool, str | None]:
    """Downloads a file, updates progress, returns (success_status, file_path_if_success)."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True) # Thread-safe due to exist_ok=True
    file_name = os.path.basename(path)

    # --- Pre-download Check ---
    if os.path.exists(path) and expected_sha1:
        actual_sha1 = get_sha1(path)
        if actual_sha1 == expected_sha1:
            if progress and task_id is not None:
                try: # Handle potential race condition if task was removed
                    file_size = os.path.getsize(path)
                    progress.update(task_id, completed=file_size, total=file_size, visible=False, description=f"[dim]Skipped {file_name}[/]")
                except Exception: pass # Ignore if task doesn't exist
            return True, path # Success, file exists and is valid
        else:
            # Use console.print for thread safety with Rich
            console.print(f"[yellow]:warning: Hash mismatch for {file_name}. Expected {expected_sha1}, got {actual_sha1}. Redownloading...[/]")
            try:
                os.remove(path)
            except OSError as e:
                console.print(f"[red]:cross_mark: Error removing mismatched file {path}: {e}[/]")
                if progress and task_id is not None:
                    try: progress.update(task_id, description=f"[red]Failed Removal {file_name}", visible=False)
                    except Exception: pass
                return False, None # Cannot proceed
    elif os.path.exists(path) and not expected_sha1:
        if progress and task_id is not None:
            try:
                file_size = os.path.getsize(path)
                progress.update(task_id, completed=file_size, total=file_size, visible=False, description=f"[dim]Skipped {file_name}[/]")
            except Exception: pass
        return True, path # Success, file exists, no hash check

    # --- Download Attempt ---
    if progress and task_id is not None:
        try: progress.update(task_id, description=f"DL {file_name}", visible=True)
        except Exception: pass # Task might not exist if check was very fast

    last_exception = None
    for attempt in range(retries):
        try:
            response = requests.get(url, stream=True, timeout=20) # Slightly shorter timeout
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))

            if progress and task_id is not None:
                try: progress.update(task_id, total=total_size, completed=0) # Reset progress on retry
                except Exception: pass

            # Ensure we have a task ID before writing
            if progress and task_id is None: # Should not happen with current logic, but safeguard
                 console.print(f"[yellow]Warning: No task ID for {file_name} download progress.[/]")

            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        if progress and task_id is not None:
                            try: progress.update(task_id, advance=len(chunk))
                            except Exception: pass # Task might be removed if completed quickly

            # --- Post-download Verification ---
            if expected_sha1:
                actual_sha1 = get_sha1(path)
                if actual_sha1 != expected_sha1:
                    last_exception = ValueError(f"Hash mismatch after download for {file_name}")
                    console.print(f"[red]:cross_mark: {last_exception}. Expected {expected_sha1}, got {actual_sha1}.[/]")
                    if os.path.exists(path): os.remove(path)
                    if attempt < retries - 1:
                        console.print(f"[yellow]:hourglass_flowing_sand: Retrying download ({attempt+2}/{retries}) for {file_name}...[/]")
                        if progress and task_id is not None:
                             try: progress.reset(task_id)
                             except Exception: pass
                        time.sleep(0.5 * (attempt + 1)) # Exponential backoff slightly
                        continue
                    else:
                        console.print(f"[bold red]:stop_sign: Max retries reached for {file_name}. Download failed.[/]")
                        if progress and task_id is not None:
                             try: progress.update(task_id, description=f"[red]Failed DL {file_name}", visible=False)
                             except Exception: pass
                        return False, None
                else:
                    # Verified successfully
                    if progress and task_id is not None:
                         try: progress.update(task_id, description=f"[green]:heavy_check_mark:[/] {file_name}", visible=False)
                         except Exception: pass
                    return True, path
            else:
                # No hash check needed, download successful
                if progress and task_id is not None:
                     try: progress.update(task_id, description=f"[green]:heavy_check_mark:[/] {file_name}", visible=False)
                     except Exception: pass
                return True, path

        except requests.exceptions.Timeout as e:
             last_exception = e
             console.print(f"[yellow]:timer_clock: Timeout downloading {file_name} on attempt {attempt+1}.[/]")
        except requests.exceptions.RequestException as e:
            last_exception = e
            console.print(f"[red]:satellite: Network error downloading {file_name}: {e}[/]")
        except OSError as e: # Catch potential file writing errors
             last_exception = e
             console.print(f"[red]:floppy_disk: File system error for {file_name}: {e}[/]")
        except Exception as e: # Catch unexpected errors
            last_exception = e
            console.print(f"[bold red]:boom: Unexpected error during download of {file_name}: {e}[/]")

        # Common handling for retries/failure after exception
        if os.path.exists(path): # Clean up potentially corrupted file
            try: os.remove(path)
            except OSError: pass # Ignore if removal fails

        if attempt < retries - 1:
            console.print(f"[yellow]:hourglass_flowing_sand: Retrying download ({attempt+2}/{retries}) for {file_name}...[/]")
            if progress and task_id is not None:
                 try: progress.reset(task_id)
                 except Exception: pass
            time.sleep(0.5 * (attempt + 1))
        else:
            console.print(f"[bold red]:stop_sign: Max retries reached for {file_name} after error: {last_exception}. Download failed.[/]")
            if progress and task_id is not None:
                 try: progress.update(task_id, description=f"[red]Failed DL {file_name}", visible=False)
                 except Exception: pass
            return False, None

    return False, None # Should only be reached if all retries fail


def check_rules(rules):
    """Checks if the rules allow the library/native for the current OS."""
    # (Same as before)
    if not rules: return True
    allow = False
    current_os = platform.system().lower()
    os_name_map = {"windows": "windows", "linux": "linux", "darwin": "osx"}
    minecraft_os = os_name_map.get(current_os)
    if not minecraft_os: return True

    for rule in rules:
        action = rule['action'] == 'allow'
        applies = True
        if 'os' in rule:
            rule_os = rule['os'].get('name')
            if rule_os and minecraft_os != rule_os:
                applies = False
            # TODO: Add 'arch' and 'version' checks
        if applies:
            allow = action
    return allow

# Modified extract_natives to return success status
def extract_natives(native_jar_path: str, extract_dir: str, progress: Progress | None = None, task_id: TaskID | None = None) -> bool:
    """Extracts native libraries, returns True on success, False on failure."""
    native_name = os.path.basename(native_jar_path)
    if progress and task_id is not None:
        try: progress.update(task_id, description=f"Extract {native_name}", total=1, completed=0, visible=True)
        except Exception: pass

    os.makedirs(extract_dir, exist_ok=True) # Safe for concurrent calls
    try:
        with zipfile.ZipFile(native_jar_path, 'r') as jar:
            # Check if zipfile is valid before proceeding further (basic check)
            # CORRECTED INDENTATION:
            if jar.testzip() is not None:
                raise zipfile.BadZipFile(f"Corrupted ZIP detected in {native_name}")

            members_to_extract = [m for m in jar.namelist() if not m.startswith('META-INF/')]
            # Extracting members one by one might be slightly safer for concurrency
            # but extractall is generally fine if target dir creation is handled.
            jar.extractall(extract_dir, members=members_to_extract)

        if progress and task_id is not None:
            try: progress.update(task_id, completed=1, description=f"[green]:package:[/] {native_name}", visible=False)
            except Exception: pass
        return True
    except zipfile.BadZipFile as e:
        console.print(f"[red]:broken_heart: Bad ZIP file: {native_name} - {e}[/]")
        if progress and task_id is not None:
             try: progress.update(task_id, description=f"[red]Bad ZIP {native_name}", visible=False)
             except Exception: pass
        # Optionally delete the corrupted file
        # try: os.remove(native_jar_path)
        # except OSError: pass
        return False
    except Exception as e:
        console.print(f"[red]:boom: Error extracting {native_name}: {e.__class__.__name__} - {e}[/]")
        if progress and task_id is not None:
             try: progress.update(task_id, description=f"[red]Extract Fail {native_name}", visible=False)
             except Exception: pass
        return False

# --- Main Logic ---

def main():
    console.print(Panel(f" [bold cyan]Minecraft Launcher (Offline - Rich/MT)[/] | Version: [yellow]{TARGET_VERSION}[/] | User: [yellow]{OFFLINE_USERNAME}[/] ", title="PyLauncher", subtitle=f"Dir: {MINECRAFT_DIR}", border_style="blue"))

    # --- Setup Directories ---
    # (Same as before)
    libs_dir = os.path.join(MINECRAFT_DIR, "libraries")
    assets_dir = os.path.join(MINECRAFT_DIR, "assets")
    versions_dir = os.path.join(MINECRAFT_DIR, "versions")
    try:
        os.makedirs(libs_dir, exist_ok=True)
        os.makedirs(os.path.join(assets_dir, "objects"), exist_ok=True)
        os.makedirs(os.path.join(assets_dir, "indexes"), exist_ok=True)
        os.makedirs(versions_dir, exist_ok=True)
    except OSError as e:
        console.print(f"[bold red]Error creating directories: {e}[/]")
        return

    # --- Progress Bar Setup ---
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False, # Keep finished tasks for a bit
        # auto_refresh=False # Managed by Live display context below
    )

    # Use Live display to manage updates to overall task description smoothly
    overall_task = progress.add_task("[bold blue]Overall Progress", total=7) # Added 1 step for init
    live = Live(progress, console=console, refresh_per_second=10, vertical_overflow="visible")

    with live: # Start the live display

        progress.update(overall_task, description="[bold blue]Initializing...")

        # --- 1. Get Version Manifest ---
        progress.update(overall_task, description="[bold blue]Fetching Version Manifest...")
        manifest_task = progress.add_task("Fetching manifest", total=1, visible=False) # Hide simple tasks quickly
        version_manifest = None
        try:
            manifest_response = requests.get(VERSION_MANIFEST_URL, timeout=10)
            manifest_response.raise_for_status()
            version_manifest = manifest_response.json()
            progress.update(manifest_task, completed=1, description="[green]:globe_with_meridians:[/] Manifest", visible=False)
        except requests.exceptions.RequestException as e:
            console.print(f"[bold red]:cross_mark: Error fetching version manifest: {e}[/]")
            progress.update(manifest_task, description="[red]Manifest Failed", visible=False)
            return # Critical failure
        except json.JSONDecodeError:
            console.print("[bold red]:cross_mark: Error decoding version manifest JSON.[/]")
            progress.update(manifest_task, description="[red]Manifest Decode Failed", visible=False)
            return # Critical failure
        progress.advance(overall_task)

        # --- 2. Find Target Version URL & Get Specific Version JSON ---
        progress.update(overall_task, description=f"[bold blue]Fetching {TARGET_VERSION} Info...")
        version_url = None
        for v in version_manifest.get('versions', []):
            if v.get('id') == TARGET_VERSION:
                version_url = v.get('url')
                break

        if not version_url:
            console.print(f"[bold red]:cross_mark: Version {TARGET_VERSION} not found in manifest.[/]")
            return

        version_json_path = os.path.join(versions_dir, TARGET_VERSION, f"{TARGET_VERSION}.json")
        os.makedirs(os.path.dirname(version_json_path), exist_ok=True)
        version_json_task = progress.add_task(f"Version JSON {TARGET_VERSION}", start=False, visible=False) # Hide simple tasks
        success, _ = download_file(version_url, version_json_path, progress=progress, task_id=version_json_task)
        if not success:
             console.print(f"[bold red]:cross_mark: Failed to download version JSON for {TARGET_VERSION}[/]")
             return

        version_data = None
        try:
            with open(version_json_path, 'r', encoding='utf-8') as f:
                version_data = json.load(f)
        except FileNotFoundError:
            console.print(f"[bold red]:cross_mark: Version JSON not found at {version_json_path} (download failed?).[/]")
            return
        except json.JSONDecodeError:
            console.print(f"[bold red]:cross_mark: Error decoding version JSON: {version_json_path}[/]")
            return
        progress.advance(overall_task)

        # --- 3. Download Client JAR ---
        progress.update(overall_task, description="[bold blue]Checking Client JAR...")
        client_jar_info = version_data.get('downloads', {}).get('client')
        if not client_jar_info or 'url' not in client_jar_info or 'sha1' not in client_jar_info:
            console.print("[bold red]:cross_mark: Client JAR download information incomplete/missing.[/]")
            return

        client_jar_path = os.path.join(versions_dir, TARGET_VERSION, f"{TARGET_VERSION}.jar")
        client_task = progress.add_task(f"Client {TARGET_VERSION}.jar", start=False, visible=False) # Hide simple tasks
        success, client_jar_path_result = download_file(client_jar_info['url'], client_jar_path, client_jar_info['sha1'], progress=progress, task_id=client_task)
        if not success:
            console.print("[bold red]:cross_mark: Failed to download client JAR.[/]")
            return
        client_jar_path = client_jar_path_result # Ensure we use the returned path
        progress.advance(overall_task)

        # --- 4. Process Libraries (Concurrent Downloads) ---
        progress.update(overall_task, description="[bold blue]Checking Libraries...")
        library_paths = []
        native_lib_info = [] # Store tuples of (path, url, sha1) for natives
        libs_to_process = version_data.get('libraries', [])
        libs_task = progress.add_task("Checking Libraries", total=len(libs_to_process))

        current_os = platform.system().lower()
        os_name_map = {"windows": "windows", "linux": "linux", "darwin": "osx"}
        minecraft_os = os_name_map.get(current_os)

        futures = {} # Store {future: (is_native, lib_name)}
        required_libs = [] # List of (is_native, lib_path, url, sha1, lib_name)

        # First pass: Identify required libs and check cache
        for i, lib in enumerate(libs_to_process):
            lib_name = lib.get('name', f'lib_{i}')
            progress.update(libs_task, description=f"Check Libs ({i+1}/{len(libs_to_process)}) - {lib_name.split(':')[-1]}")

            if not check_rules(lib.get('rules')):
                progress.advance(libs_task)
                continue

            artifact = None
            is_native = False
            lib_path = None
            url = None
            sha1_val = None

            # Determine artifact, path, url, sha1
            if 'natives' in lib and minecraft_os in lib['natives']:
                classifier = lib['natives'][minecraft_os].replace("${arch}", platform.machine().replace('AMD64', '64').replace('x86_64', '64'))
                if 'classifiers' in lib.get('downloads', {}):
                    artifact = lib['downloads']['classifiers'].get(classifier)
                    if artifact: is_native = True
            if not artifact and 'artifact' in lib.get('downloads', {}):
                 artifact = lib['downloads']['artifact']
                 is_native = False
            if not artifact or not artifact.get('path') or not artifact.get('url') or not artifact.get('sha1'):
                # console.print(f"[yellow]Warning: Skipping library {lib_name} due to missing info.[/]")
                progress.advance(libs_task)
                continue

            lib_path = os.path.join(libs_dir, artifact['path'])
            url = artifact['url']
            sha1_val = artifact['sha1']

            # Check cache sync
            needs_download = True
            if os.path.exists(lib_path) and sha1_val:
                actual_sha1 = get_sha1(lib_path)
                if actual_sha1 == sha1_val:
                    needs_download = False
                    # Add path directly if valid and exists
                    if is_native:
                        native_lib_info.append(lib_path) # Store path for extraction later
                    else:
                        library_paths.append(lib_path) # Add to classpath list
                    progress.update(libs_task, description=f"[dim]Cached Lib: {lib_name.split(':')[-1]}")
                else:
                    # Hash mismatch, will be added to required_libs for download
                    pass

            if needs_download:
                required_libs.append((is_native, lib_path, url, sha1_val, lib_name))

            progress.advance(libs_task) # Advance check progress

        progress.update(libs_task, description="[green]Library Check Complete[/]", visible=False) # Hide check bar

        # Second pass: Download required libs concurrently
        if required_libs:
            libs_download_task = progress.add_task("[cyan]Downloading Libraries", total=len(required_libs))
            with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS, thread_name_prefix="LibDL") as executor:
                for is_native, lib_path, url, sha1_val, lib_name in required_libs:
                    # Create a unique task ID for each download
                    dl_task_id = progress.add_task(f"Lib {lib_name.split(':')[-1]}", start=False, visible=False) # Initially hidden
                    future = executor.submit(download_file, url, lib_path, sha1_val, progress=progress, task_id=dl_task_id)
                    futures[future] = (is_native, lib_path, lib_name) # Store needed info with future

                for future in as_completed(futures):
                    is_native, lib_path_result, lib_name = futures[future]
                    try:
                        success, result_path = future.result()
                        if success and result_path:
                            if is_native:
                                native_lib_info.append(result_path)
                            else:
                                library_paths.append(result_path)
                        else:
                             console.print(f"[bold red]:cross_mark: Failed to ensure library: {lib_name}. Launch may fail.[/]")
                    except Exception as exc:
                        console.print(f"[bold red]:boom: Error processing library {lib_name}: {exc}[/]")
                    progress.advance(libs_download_task) # Advance download progress

            progress.update(libs_download_task, description="[green]Libraries Downloaded[/]", visible=False) # Hide download bar
        else:
            console.print("[dim]All required libraries are cached.[/]")

        progress.advance(overall_task)

        # --- 5. Extract Natives (Concurrent) ---
        progress.update(overall_task, description="[bold blue]Extracting Natives...")
        natives_dir = os.path.join(versions_dir, TARGET_VERSION, f"{TARGET_VERSION}-natives")
        extracted_native_paths = [] # Store paths of successfully extracted jars for potential cleanup

        if native_lib_info:
             # Clean old natives dir *before* extraction starts
            if os.path.exists(natives_dir):
                try:
                    shutil.rmtree(natives_dir)
                    os.makedirs(natives_dir) # Recreate after cleaning
                except OSError as e:
                    console.print(f"[yellow]Warning: Could not fully clean natives directory {natives_dir}: {e}[/]")

            natives_extract_task = progress.add_task("[cyan]Extracting Natives", total=len(native_lib_info))
            extract_futures = {}
            with ThreadPoolExecutor(max_workers=MAX_EXTRACT_WORKERS, thread_name_prefix="NativeExtract") as executor:
                for native_jar in native_lib_info:
                    extract_task_id = progress.add_task(f"Extract {os.path.basename(native_jar)}", total=1, start=False, visible=False) # Initially hidden
                    future = executor.submit(extract_natives, native_jar, natives_dir, progress=progress, task_id=extract_task_id)
                    extract_futures[future] = native_jar

                for future in as_completed(extract_futures):
                    native_jar_path = extract_futures[future]
                    try:
                        success = future.result()
                        if not success:
                            console.print(f"[yellow]Warning: Failed to extract natives from {os.path.basename(native_jar_path)}. Game might crash.[/]")
                        else:
                            extracted_native_paths.append(native_jar_path)
                    except Exception as exc:
                         console.print(f"[bold red]:boom: Error during native extraction for {os.path.basename(native_jar_path)}: {exc}[/]")
                    progress.advance(natives_extract_task)

            progress.update(natives_extract_task, description="[green]Natives Extracted[/]", visible=False)
        else:
             console.print("[dim]No native libraries found or needed for this OS/version.[/]")

        progress.advance(overall_task)

        # --- 6. Process Assets (Concurrent Downloads) ---
        progress.update(overall_task, description="[bold blue]Checking Assets...")
        asset_index_info = version_data.get('assetIndex')
        if not asset_index_info or 'id' not in asset_index_info or 'url' not in asset_index_info or 'sha1' not in asset_index_info:
             console.print("[bold red]:cross_mark: Asset Index information incomplete/missing.[/]")
             return # Cannot proceed without asset index

        asset_index_id = asset_index_info['id']
        asset_index_url = asset_index_info['url']
        asset_index_sha1 = asset_index_info['sha1']
        asset_index_path = os.path.join(assets_dir, "indexes", f"{asset_index_id}.json")

        asset_index_task = progress.add_task(f"Asset Index {asset_index_id}", start=False, visible=False)
        success, _ = download_file(asset_index_url, asset_index_path, asset_index_sha1, progress=progress, task_id=asset_index_task)
        if not success:
            console.print("[bold red]:cross_mark: Failed to download asset index.[/]")
            return

        asset_index = None
        try:
            with open(asset_index_path, 'r', encoding='utf-8') as f:
                asset_index = json.load(f)
        except Exception as e:
            console.print(f"[bold red]:cross_mark: Failed to read asset index {asset_index_path}: {e}[/]")
            return

        assets_object_dir = os.path.join(assets_dir, "objects")
        assets_to_process = asset_index.get('objects', {})
        total_assets = len(assets_to_process)
        assets_task = progress.add_task("Checking Assets", total=total_assets)
        asset_futures = {}
        required_assets = [] # List of (name, path, url, hash)
        download_count = 0

        # First pass: Identify required assets and check cache
        for i, (asset_name, asset_data) in enumerate(assets_to_process.items()):
            progress.update(assets_task, description=f"Check Assets ({i+1}/{total_assets})")
            asset_hash = asset_data.get('hash')
            if not asset_hash or len(asset_hash) < 2:
                progress.advance(assets_task)
                continue

            asset_sub_dir = asset_hash[:2]
            asset_file_dir = os.path.join(assets_object_dir, asset_sub_dir)
            asset_file_path = os.path.join(asset_file_dir, asset_hash)
            asset_url = f"{ASSET_BASE_URL}{asset_sub_dir}/{asset_hash}"

            needs_download = True
            if os.path.exists(asset_file_path):
                 actual_sha1 = get_sha1(asset_file_path)
                 if actual_sha1 == asset_hash:
                     needs_download = False
                 else:
                     # Hash mismatch, needs download
                     pass

            if needs_download:
                 required_assets.append((asset_name, asset_file_path, asset_url, asset_hash))

            progress.advance(assets_task)

        progress.update(assets_task, description="[green]Asset Check Complete[/]", visible=False)

        # Second pass: Download required assets concurrently
        if required_assets:
            assets_download_task = progress.add_task("[cyan]Downloading Assets", total=len(required_assets))
            with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS, thread_name_prefix="AssetDL") as executor:
                for asset_name, asset_file_path, asset_url, asset_hash in required_assets:
                    dl_task_id = progress.add_task(f"Asset {asset_hash[:7]}...", start=False, visible=False) # Hide individual asset tasks
                    future = executor.submit(download_file, asset_url, asset_file_path, asset_hash, progress=progress, task_id=dl_task_id)
                    asset_futures[future] = (asset_name, asset_hash)

                for future in as_completed(asset_futures):
                    asset_name, asset_hash = asset_futures[future]
                    try:
                        success, _ = future.result()
                        if success:
                             download_count += 1
                        else:
                             console.print(f"[red]:cross_mark: Failed to ensure asset: {asset_name} ({asset_hash})[/]")
                    except Exception as exc:
                         console.print(f"[bold red]:boom: Error processing asset {asset_name} ({asset_hash}): {exc}[/]")
                    progress.advance(assets_download_task)

            progress.update(assets_download_task, description=f"[green]Assets Downloaded ({download_count})[/]", visible=False)
        else:
             console.print("[dim]All required assets are cached.[/]")

        progress.advance(overall_task)

        progress.update(overall_task, description="[bold blue]Constructing Launch Command...")
        main_class = version_data.get('mainClass')
        if not main_class:
            console.print("[bold red]Error: 'mainClass' not found in version JSON.[/]")
            live.stop()  # Stop live display before exiting
            return

        classpath_separator = ';' if platform.system() == "Windows" else ':'
        classpath = classpath_separator.join([client_jar_path] + library_paths)

        # Arguments Parsing (remains the same)
        jvm_args_templates = []
        game_args_templates = []
        # ... [Keep the existing logic to populate jvm_args_templates and game_args_templates] ...
        if 'arguments' in version_data:
            if 'jvm' in version_data['arguments']:
                for arg in version_data['arguments']['jvm']:
                    if isinstance(arg, str):
                        jvm_args_templates.append(arg)
                    elif isinstance(arg, dict) and check_rules(arg.get('rules')):
                        value = arg.get('value')
                        if isinstance(value, str):
                            jvm_args_templates.append(value)
                        elif isinstance(value, list):
                            jvm_args_templates.extend(value)
            if 'game' in version_data['arguments']:
                for arg in version_data['arguments']['game']:
                    if isinstance(arg, str):
                        game_args_templates.append(arg)
                    elif isinstance(arg, dict) and check_rules(arg.get('rules')):
                        value = arg.get('value')
                        if isinstance(value, str):
                            game_args_templates.append(value)
                        elif isinstance(value, list):
                            game_args_templates.extend(value)
        elif 'minecraftArguments' in version_data:  # Legacy fallback
            console.print(
                "[yellow]Warning: Using legacy 'minecraftArguments'. Argument parsing might be incomplete.[/]")
            # Split legacy arguments BUT we will override auth args later
            game_args_templates = version_data['minecraftArguments'].split(' ')
            jvm_args_templates.append("-Djava.library.path=${natives_directory}")
            jvm_args_templates.append("-cp")
            jvm_args_templates.append("${classpath}")
        else:
            console.print("[bold red]Error: Could not find 'arguments' or 'minecraftArguments' in version JSON.[/]")
            live.stop()
            return

        # Placeholder replacements
        auth_uuid = uuid.uuid4().hex
        abs_minecraft_dir = os.path.abspath(MINECRAFT_DIR)
        abs_assets_dir = os.path.abspath(assets_dir)
        abs_natives_dir = os.path.abspath(natives_dir)
        abs_libs_dir = os.path.abspath(libs_dir)

        # *** Store auth details separately ***
        auth_details = {
            "username": OFFLINE_USERNAME,
            "uuid": auth_uuid,
            "access_token": "0",  # Use "0" for offline mode token
            "user_type": "legacy"  # Or potentially "msa", though legacy usually works for offline
        }

        replacements = {
            "${auth_player_name}": auth_details["username"],  # Reference stored details
            "${version_name}": TARGET_VERSION,
            "${game_directory}": abs_minecraft_dir,
            "${assets_root}": abs_assets_dir,
            "${assets_index_name}": asset_index_id,
            "${auth_uuid}": auth_details["uuid"],  # Reference stored details
            "${auth_access_token}": auth_details["access_token"],  # Reference stored details
            # "${clientid}": "N/A", # Often not needed directly in args
            # "${auth_xuid}": "N/A", # Often not needed directly in args
            "${user_type}": auth_details["user_type"],  # Reference stored details
            "${version_type}": version_data.get('type', 'release'),
            "${natives_directory}": abs_natives_dir,
            "${launcher_name}": "PyLauncherRichMT",
            "${launcher_version}": "0.3",
            "${classpath}": classpath,
            "${library_directory}": abs_libs_dir,
            "${classpath_separator}": classpath_separator,
        }

        # Process JVM Args (Replace placeholders)
        processed_jvm_args = []
        for arg_template in jvm_args_templates:
            processed_arg = arg_template
            for key, value in replacements.items():
                processed_arg = processed_arg.replace(key, value)
            processed_jvm_args.append(processed_arg)

        # Process Game Args (Replace placeholders)
        processed_game_args = []
        # Keep track of which auth args we found placeholders for
        found_auth_args = {'username': False, 'uuid': False, 'accessToken': False, 'userType': False}
        skip_next = False
        for i, arg_template in enumerate(game_args_templates):
            if skip_next:
                skip_next = False
                continue

            processed_arg = arg_template
            # Check if this argument *is* an auth placeholder itself
            if processed_arg == '--username':
                found_auth_args['username'] = True
            elif processed_arg == '--uuid':
                found_auth_args['uuid'] = True
            elif processed_arg == '--accessToken':
                found_auth_args['accessToken'] = True
            elif processed_arg == '--userType':
                found_auth_args['userType'] = True

            # Replace placeholders within the argument string
            for key, value in replacements.items():
                processed_arg = processed_arg.replace(key, value)
            processed_game_args.append(processed_arg)

            # If the *next* argument template is a known auth placeholder, process it now
            if i + 1 < len(game_args_templates):
                next_arg_template = game_args_templates[i + 1]
                if next_arg_template in ["${auth_player_name}", "${auth_uuid}", "${auth_access_token}", "${user_type}"]:
                    processed_next_arg = next_arg_template
                    for key, value in replacements.items():
                        processed_next_arg = processed_next_arg.replace(key, value)
                    processed_game_args.append(processed_next_arg)
                    skip_next = True  # Skip the next argument in the main loop

        # *** Explicitly add missing authentication arguments ***
        # This ensures they are present even if not found via placeholders in version.json
        if not found_auth_args['username']:
            processed_game_args.extend(["--username", auth_details["username"]])
            console.print("[dim yellow]Note: Explicitly added --username argument.[/]")
        if not found_auth_args['uuid']:
            processed_game_args.extend(["--uuid", auth_details["uuid"]])
            console.print("[dim yellow]Note: Explicitly added --uuid argument.[/]")
        if not found_auth_args['accessToken']:
            processed_game_args.extend(["--accessToken", auth_details["access_token"]])
            console.print("[dim yellow]Note: Explicitly added --accessToken argument.[/]")
        # userType is sometimes optional or handled differently, add if missing and desired
        # if not found_auth_args['userType']:
        #    processed_game_args.extend(["--userType", auth_details["user_type"]])
        #    console.print("[dim yellow]Note: Explicitly added --userType argument.[/]")

        # Construct the final command
        command = [JAVA_EXECUTABLE] + processed_jvm_args + [main_class] + processed_game_args
        progress.advance(overall_task)
        progress.update(overall_task, description="[bold green]:rocket: Ready to Launch[/]")
        progress.update(overall_task, visible=False)

    # Check the launch argument and if there is "--demo" remove it
    if "--demo" in command:
        command.remove("--demo")
        console.print("[dim yellow]Note: Removed --demo argument from launch command.[/]")

    # --- End of Live/Progress Context ---
    # Progress bars stop updating here

    console.print(Rule("[bold green]Launch Command Prepared[/]"))
    console.print(f"[dim]{' '.join(command)}[/]") # Uncomment to see full command easily
    console.print(f" [dim]Java: {JAVA_EXECUTABLE}[/]")
    console.print(f" [dim]Main Class: {main_class}[/]")
    console.print(f" [dim]Working Dir: {abs_minecraft_dir}[/]") # Show absolute path
    console.print(Rule("[bold yellow]Starting Minecraft...[/]"))

    # --- 8. Launch the game ---
    # (Launch logic remains the same)
    try:
        process = subprocess.Popen(command, cwd=abs_minecraft_dir, # Use absolute path for cwd
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', errors='replace',
                                   creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0) # Hide console on Windows

        # Optional: Stream output in a separate thread to avoid blocking UI thread if needed
        # ... (complex to integrate smoothly with final messages, keep simple wait for now)

        return_code = process.wait()
        console.print(Rule(f"[bold blue]Minecraft Exited (Code: {return_code})[/]"))
        if return_code != 0:
             console.print("[yellow]Minecraft may have exited with errors.[/]")
             # Retrieve and print stderr if there was an error code
             _stdout, stderr = process.communicate() # Get remaining output
             if stderr:
                 console.print("[bold red]Stderr output:[/]")
                 console.print(f"[yellow]{stderr.strip()}[/]")


    except FileNotFoundError:
        console.print(f"[bold red]:cross_mark: Error: '{JAVA_EXECUTABLE}' command not found.[/]")
        console.print("[yellow]Please ensure Java is installed and in your system's PATH,[/]")
        console.print(f"[yellow]or set JAVA_EXECUTABLE in the script.[/]")
    except Exception as e:
        console.print(f"[bold red]:boom: An error occurred while launching Minecraft: {e}[/]")
        console.print_exception(show_locals=False) # Show traceback

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]:hand: Launch cancelled by user.[/]")
    except Exception as e:
        # Catch errors happening outside the main function's try block
        console.print(f"\n[bold red]:boom: An unexpected critical error occurred:[/]")
        console.print_exception(show_locals=True)