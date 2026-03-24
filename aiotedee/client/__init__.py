"""Client classes for interacting with the Tedee API.

Class hierarchy::

    TedeeClientBase          - shared state, properties, business logic
    ├── TedeeLocalClient     - local bridge API transport + webhook management
    └── TedeeCloudClient     - cloud API transport + get_bridges()
"""

from .cloud import TedeeCloudClient
from .local import TedeeLocalClient

__all__ = ["TedeeCloudClient", "TedeeLocalClient"]
