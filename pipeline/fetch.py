"""
Downloads that survive bad connections, and checks that files are whole before we read them.

NISAR products are 1-3 GB each. asf_search's own download starts again from zero
when the connection drops, and later skips a half-written file as if it were done.
Here every product downloads to <name>.part, resumes from where it stopped
(HTTP Range), is checked against the size NASA lists, and only then gets its real
name. A broken file left by an older download is picked up and resumed.
"""
import re
import time
from pathlib import Path

import h5py

VERSION = re.compile(r"_(\d{3})$")


def latest_versions(results):
    """NASA sometimes reprocesses a product (..._001, then ..._002): keep only the newest of each."""
    best = {}
    for r in results:
        name = r.properties.get("sceneName") or ""
        m = VERSION.search(name)
        key, version = (name[:m.start()], int(m.group(1))) if m else (name, 0)
        if key not in best or version > best[key][0]:
            best[key] = (version, r)
    keep = {id(r) for _, r in best.values()}
    return [r for r in results if id(r) in keep]


def expected_size(result, name):
    listed = result.properties.get("bytes")
    if isinstance(listed, dict):
        entry = listed.get(name)
        if isinstance(entry, dict) and entry.get("bytes"):
            return int(entry["bytes"])
    return None


def is_whole(path):
    try:
        with h5py.File(path, "r"):
            return True
    except OSError:
        return False


def download(result, folder, session, tries=8):
    """Download one product into folder, resuming after dropped connections. Returns the path."""
    try:
        from asf_search.download.download import strip_auth_if_aws
        hooks = {"response": strip_auth_if_aws}
    except ImportError:                                  # older asf_search
        hooks = None
    import requests

    url = result.properties["url"]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = result.properties.get("fileName") or url.rsplit("/", 1)[-1]
    dest, part = folder / name, folder / (name + ".part")
    want = expected_size(result, name)

    if dest.exists():
        if (want is None or dest.stat().st_size == want) and is_whole(dest):
            print("    already downloaded")
            return dest
        print("    found an unfinished file; resuming it")
        dest.replace(part)

    for attempt in range(1, tries + 1):
        have = part.stat().st_size if part.exists() else 0
        if want is not None and have >= want:
            break
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with session.get(url, headers=headers, stream=True, timeout=(30, 300), hooks=hooks) as r:
                if r.status_code == 416:                 # nothing left to send
                    break
                r.raise_for_status()
                if have and r.status_code != 206:        # server ignored the range: start over
                    have = 0
                with open(part, "ab" if have else "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            if want is None or part.stat().st_size >= want:
                break
        except (requests.RequestException, OSError) as exc:
            done = part.stat().st_size / 1e9 if part.exists() else 0
            print(f"    connection dropped at {done:.2f} GB ({type(exc).__name__}); "
                  f"resuming, try {attempt}/{tries}")
            time.sleep(min(60, 5 * attempt))
    else:
        raise SystemExit(f"Couldn't finish {name} after {tries} tries. Run the same command again; "
                         "it carries on from where it stopped.")

    if not is_whole(part):
        raise SystemExit(f"{name} downloaded but isn't a readable HDF5 file. Delete {part} and try again.")
    part.replace(dest)
    return dest


TRACK = re.compile(r"NISAR_L\d_\w\w_[A-Z]+_\d{3}_(\d{3})_([AD])_")


def one_track(files):
    """Pair products from different tracks must not be mixed in one time series: keep one track.

    The track with the most files wins; the others are listed so you can move them away.
    Files whose names don't follow NASA's pattern (such as synthetic demos) are all kept.
    """
    groups = {}
    for path in files:
        m = TRACK.search(Path(path).name)
        groups.setdefault(m.groups() if m else None, []).append(path)
    named = {k: v for k, v in groups.items() if k is not None}
    if len(named) <= 1:
        return list(files)
    keep = max(named, key=lambda k: (len(named[k]), k))
    for k, paths in named.items():
        if k != keep:
            for path in paths:
                print(f"  skipping {Path(path).name}: track {int(k[0])} {'ascending' if k[1] == 'A' else 'descending'}, "
                      f"but this place uses track {int(keep[0])}. Move it out of the folder to silence this.")
    return [p for p in files if (TRACK.search(Path(p).name).groups() if TRACK.search(Path(p).name) else None) in (keep, None)]


def usable_h5(files):
    """Drop files that are half-downloaded or broken, and older versions of reprocessed products."""
    newest = {}
    for path in files:
        stem = Path(path).stem
        m = VERSION.search(stem)
        key, version = (stem[:m.start()], int(m.group(1))) if m else (stem, 0)
        if key not in newest or version > newest[key][0]:
            newest[key] = (version, path)
    latest = {str(p) for _, p in newest.values()}
    for path in files:
        if str(path) not in latest:
            print(f"  skipping {Path(path).name}: NASA has a newer version of this product")
    files = [p for p in files if str(p) in latest]
    good = []
    for path in files:
        if is_whole(path):
            good.append(path)
        else:
            print(f"  skipping {Path(path).name}: incomplete or damaged. Run the download command again to finish it.")
    return good
