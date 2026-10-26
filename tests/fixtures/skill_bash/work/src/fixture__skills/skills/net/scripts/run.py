#!/usr/bin/env python3
"""Usage: run.py --week N. Calls requests.get on the report API."""
import shutil
import requests

# requests.post would upload; we do not.
def main():
    r = requests.get("https://api.example.com/report")
    shutil.rmtree("out", ignore_errors=True)
    return r.text
