from setuptools import setup, find_packages

setup(
    name="gsboard",
    version="0.1.0",
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
