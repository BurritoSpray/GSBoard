from setuptools import setup, find_packages
from gsboard import __version__

setup(
    name="gsboard",
    version=__version__,
    packages=find_packages(),
    install_requires=[
        "PyQt6>=6.5",
        "sounddevice>=0.4",
        "soundfile>=0.12",
        "numpy>=1.24",
        "pynput>=1.7",
        "evdev>=1.6; sys_platform == 'linux'",
        "dbus-python>=1.3; sys_platform == 'linux'",
    ],
    entry_points={
        "console_scripts": [
            "gsboard=gsboard.main:main",
        ],
    },
    python_requires=">=3.10",
)
