# Python Tedee Async Client Package

This is a Tedee Lock Client package. It is an async implementation of [joerg65's original package](https://github.com/joerg65/pytedee.git).

## Install:
### From pip
```
pip install pytedee-async
```

### Locally
```python
pipenv install -e .
# or
python3 setup.py install
```

## Try it out
- Generate personal key. Instructions: https://tedee-tedee-api-doc.readthedocs-hosted.com/en/latest/howtos/authenticate.html#personal-access-key
  Minimal scopes required for enable integration are:
    - Devices.Read
    - Lock.Operate
- with `example.py`: Create a file `config.json` next to `example.py`:
```json
  {
  "personalToken": "<your token>"
  }
```
cd into the directory of those to files and run
```
python example.py
```

- Initiate an instance of `TedeeClient`
```python
from pytedee_async import TedeeClient

pk = "<your PersonalKey>"
# through init
client = TedeeClient(pk) # is initialized with no locks
client.get_locks() # get the locks

# through classmethod
# will initialize directly with all locks you have
client = await TedeeClient.create(pk)
```

- the locks are avialable in a dictionary `client.locks_dict` with the key of the dict being the serial number of each lock, or in a list `client.locks`
