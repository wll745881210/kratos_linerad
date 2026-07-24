from setuptools import setup, find_packages

setup(
    name="line_rt_interface",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "scipy",
        "matplotlib",
    ],
    extras_require={
        "ui": ["ipywidgets"],
        "web": ["panel"],
        "all": ["ipywidgets", "panel", "requests"],
    },
    entry_points={
        "console_scripts": [
            "line-rt=cli:main",
        ],
    },
)
