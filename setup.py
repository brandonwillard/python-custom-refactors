#!/usr/bin/env python
# import versioneer

import setuptools

from os.path import exists


setuptools.setup(
    name="python-custom-refactors",
    # version=versioneer.get_version(),
    # cmdclass=versioneer.get_cmdclass(),
    description="Assorted Python project refactors.",
    long_description=open("README.md").read() if exists("README.md") else "",
    long_description_content_type="text/markdown",
    maintainer="Brandon T. Willard",
    maintainer_email="brandonwillard+kanren@gmail.com",
    version="0.0.1",
    url="https://github.com/brandonwillard/python-custom-refactors",
    license="MIT",
    packages=setuptools.find_packages(),
    python_requires=">=3.6",
    zip_safe=False,
    install_requires=["libcst"],
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Libraries",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
