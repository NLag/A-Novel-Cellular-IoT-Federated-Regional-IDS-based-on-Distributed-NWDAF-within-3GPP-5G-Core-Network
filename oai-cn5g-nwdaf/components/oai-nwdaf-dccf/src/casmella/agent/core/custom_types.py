"""Custom types to be used by the Agent.
"""
# standard
from threading import Lock, Thread
from time import time, sleep

# ============================
# Custom types
# ============================
class ThreadSafeDict(dict):
    """A thread-safe dictionary implementation.

    This class extends the built-in `dict` to provide thread-safe operations.
    It uses a threading.Lock to ensure that all operations modifying the dictionary
    are thread-safe, making it suitable for use in multi-threaded environments.

    Example:
    > ts_dict = ThreadSafeDict()
    > ts_dict['key'] = 'value'
    > print(ts_dict['key'])
    'value'
    """
    def __init__(self, /, *args, **kwargs):
        """Initializes the ThreadSafeDict with optional initial data.

        Args:
            *args: Variable length argument list for initial data.
            **kwargs: Arbitrary keyword arguments for initial data.
        """
        super().__init__(*args, **kwargs)
        self._lock = Lock()

    def __repr__(self, /) -> str:
        """Returns a string representation of the dictionary in a thread-safe manner.

        Returns:
            str: A string representation of the dictionary.
        """
        with self._lock:
            return super().__repr__()

    def __getitem__(self, key, /):
        """Gets the item associated with the given key in a thread-safe manner.

        Args:
            key (Any): The key to retrieve from the dictionary.

        Returns:
            Any: The value associated with the given key.
        """
        with self._lock:
            return super().__getitem__(key)

    def __setitem__(self, key, value, /):
        """Sets the item for the given key in a thread-safe manner.

        Args:
            key (Any): The key to set in the dictionary.
            value (Any): The value to set for the given key.
        """
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key, /):
        """Deletes the item associated with the given key in a thread-safe manner.

        Args:
            key (Any): The key to delete from the dictionary.
        """
        with self._lock:
            super().__delitem__(key)

    def __contains__(self, key, /) -> bool:
        """Checks if the given key is in the dictionary in a thread-safe manner.

        Args:
            key (Any): The key to check in the dictionary.

        Returns:
            bool: True if the key is in the dictionary, False otherwise.
        """
        with self._lock:
            return super().__contains__(key)

    def __len__(self, /) -> int:
        """Returns the number of items in the dictionary in a thread-safe manner.

        Returns:
            int: The number of items in the dictionary.
        """
        with self._lock:
            return super().__len__()

    def __iter__(self, /):
        """Returns an iterator over the dictionary's keys in a thread-safe manner.

        Returns:
            iterator: An iterator over the dictionary's keys.
        """
        with self._lock:
            return super().__iter__()


class ThreadSafeTtlDict(ThreadSafeDict):
    """A thread-safe dictionary with TTL (Time-To-Live) for each item.

    This class extends `ThreadSafeDict` to provide a thread-safe dictionary
    where each item has a TTL (Time-To-Live) value. Items that exceed their
    TTL are automatically removed from the dictionary.

    Example:
    > ts_ttl_dict = ThreadSafeTtlDict(ttl=10, period=5, maxsize=500)
    > ts_ttl_dict['key'] = 'value'
    > print(ts_ttl_dict['key'])
    'value'
    """
    def __init__(self, ttl: int|float=20, period: int|float=20, maxsize: int=1000, /, *args, **kwargs):
        """Initializes the ThreadSafeTtlDict with TTL, cleanup period, and maximum size.

        Args:
            ttl (int | float, optional): The time-to-live (in seconds) for each item. Defaults to 20.
            period (int | float, optional): The period (in seconds) for the cleanup thread to run. Defaults to 20.
            maxsize (int, optional): The maximum size of the dictionary. Defaults to 1000.
        """
        super().__init__(*args, **kwargs)
        self.ttl = float(ttl)
        self.period = period
        self.maxsize = maxsize
        Thread(
            target=self.__cleanup__,
            name='ThreadSafeTtlDict.__cleanup__'
        ).start()

    def __getitem__(self, key, /):
        """Gets the item associated with the given key and refreshes its TTL.

        Args:
            key (Any): The key to retrieve from the dictionary.

        Returns:
            Any: The value associated with the given key.
        """
        value = super().__getitem__(key)[0]
        value = (value, time())
        super().__setitem__(key, value)
        return value[0]  # return the value without timestamp

    def __setitem__(self, key, value, /):
        """Sets the item for the given key with the current timestamp.

        Args:
            key (Any): The key to set in the dictionary.
            value (Any): The value to set for the given key.
        """
        #if len(self) >= self.maxsize:
        #    oldest_key = min(self, key=lambda k: self[k][1])
        #    del self[oldest_key]
        value = (value, time())
        super().__setitem__(key, value)

    def __cleanup__iteration__(self):
        """Performs a single iteration of cleanup, removing expired items.
        """
        now = time()
        for key, (_value, timestamp) in list(self.items()):
            if now - timestamp > self.ttl:
                del self[key]

    def __cleanup__(self):
        """Continuously runs the cleanup process at the specified period.
        """
        while True:
            self.__cleanup__iteration__()
            sleep(self.period)
