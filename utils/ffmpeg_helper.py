import os
import sys
import stat
import shutil
import tarfile
import tempfile
import urllib.request

def which_ffmpeg():
    """Return path to ffmpeg if available on PATH, otherwise None."""
    return shutil.which('ffmpeg')


def _download_and_extract(url: str, dest_dir: str) -> str | None:
    try:
        os.makedirs(dest_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix='.tar.xz')
        os.close(fd)
        urllib.request.urlretrieve(url, tmp_path)
        with tarfile.open(tmp_path, 'r:xz') as tf:
            members = tf.getmembers()
            # extract ffmpeg and ffprobe
            for m in members:
                name = os.path.basename(m.name)
                if name in ('ffmpeg', 'ffprobe'):
                    m.name = name  # strip nested dirs
                    tf.extract(m, path=dest_dir)
        os.remove(tmp_path)
        ff = os.path.join(dest_dir, 'ffmpeg')
        fp = os.path.join(dest_dir, 'ffprobe')
        for p in (ff, fp):
            try:
                st = os.stat(p)
                os.chmod(p, st.st_mode | stat.S_IEXEC)
            except Exception:
                pass
        return ff if os.path.exists(ff) else None
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return None


def ensure_ffmpeg(dest_bin_dir: str | None = None) -> str | None:
    """Ensure ffmpeg is available. Returns path to ffmpeg if available, otherwise None.

    On Linux x86_64, if ffmpeg missing, attempt to download a static build
    (johnvansickle) into `dest_bin_dir` (defaults to ./bin) and add it to
    the process PATH so the running bot can use it without a system install.
    """
    path = which_ffmpeg()
    if path:
        return path

    # Only attempt auto-install on linux x86_64
    if sys.platform.startswith('linux') and (sys.maxsize > 2**32):
        if dest_bin_dir is None:
            dest_bin_dir = os.path.join(os.getcwd(), 'bin')
        url = 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz'
        ff = _download_and_extract(url, dest_bin_dir)
        if ff:
            # Prepend dest_bin_dir to PATH for this process
            os.environ['PATH'] = dest_bin_dir + os.pathsep + os.environ.get('PATH', '')
            return shutil.which('ffmpeg') or ff
    # For macOS or other platforms, do not attempt auto-install — return None
    return None
