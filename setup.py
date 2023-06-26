'''
Created on 01.11.2020

@author: joerg
'''
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pytedee_async", 
    version="0.0.6",
    author="Josef Zweck",
    author_email="24647999+zweckj@users.noreply.github.com",
    description="A Tedee Lock Client package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zweckj/pytedee_async",
    packages=setuptools.find_packages(),
    install_requires=['aiohttp', 'asyncio'],
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
