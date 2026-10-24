import sys

path = "/home/deni999/mysite"
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
