"""Setup script for airborne-gimbal package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="airborne-gimbal",
    version="0.1.0",
    author="gtraines",
    description="Control software for dual gimbals on fixed-wing drones",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gtraines/airborne-gimbal",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: System :: Hardware :: Hardware Drivers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "airborne-gimbal=airborne_gimbal.main:main",
        ],
    },
)
