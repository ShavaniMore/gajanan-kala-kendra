import os

_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), ".env")
if os.path.exists(_path):
    with open(_path, encoding="utf8") as _fh:
        for _line in _fh:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
