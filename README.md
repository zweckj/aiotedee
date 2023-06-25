# Python Tedee Async Client Package

This is a Tedee Lock Client package. It is an async implementation of [joerg65's original package](https://github.com/joerg65/pytedee.git).

## Install:

pipenv install -e .

or

python3 setup.py install

## Try it out
with the example.py:

- Generate personal key. Instructions: https://tedee-tedee-api-doc.readthedocs-hosted.com/en/latest/howtos/authenticate.html#personal-access-key
  Minimal scopes required for enable integration are:
    - Devices.Read
    - Lock.Operate
- Edit personalKey with generated value.

If module six generates erorr:<br/>
Ensure module version of six is at least 1.15.0.

pip3 install six==1.15.0
