"""Setup script for cymbal package with Cython support."""

from setuptools import setup, find_packages, Extension
from Cython.Build import cythonize

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

# Add Cython to requirements
requirements.append("Cython>=0.29.0")

# Define Cython extensions
extensions = [
    Extension(
        "cymbal.camera_gimbal.storm32_controller",
        ["cymbal/camera_gimbal/storm32_controller.pyx"],
    ),
    Extension(
        "cymbal.sensors.mpu6050",
        ["cymbal/sensors/mpu6050.pyx"],
    ),
    Extension(
        "cymbal.spotlight_gimbal.servo_controller",
        ["cymbal/spotlight_gimbal/servo_controller.pyx"],
    ),
    Extension(
        "cymbal.utils.config",
        ["cymbal/utils/config.pyx"],
    ),
    Extension(
        "cymbal.main",
        ["cymbal/main.pyx"],
    ),
]

setup(
    name="cymbal",
    version="0.1.0",
    author="gtraines",
    description="Control software for dual gimbals on fixed-wing drones (Cython optimized)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gtraines/cymbal",
    packages=find_packages(),
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",
            'embedsignature': True,
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
        }
    ),
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
        "Programming Language :: Cython",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    setup_requires=['Cython>=0.29.0'],
    entry_points={
        "console_scripts": [
            "cymbal=cymbal.main:main",
        ],
    },
)
