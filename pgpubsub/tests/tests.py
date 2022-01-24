import datetime
from typing import Dict, List, Set, Tuple
from unittest import TestCase

from pgpubsub.channel import CustomPayloadChannel
from pgpubsub.notify import _serialize


class TestCustomPayloadChannelDeserialize(TestCase):
    def test_deserialize_1(self):
        def listener_func(
            *,
            arg1: str,
            arg2: Dict[int, int],
            default_arg1: float = 0.0,
        ):
            pass

        deserialized = self._deserialize(
            listener_func, arg1='1', arg2={1:2}, default_arg1=3.4)
        self.assertEqual(
            {'arg1': '1', 'arg2': {1: 2}, 'default_arg1': 3.4},
            deserialized,
        )

    def test_deserialize_2(self):
        def listener_func(
            *,
            arg1: Dict[str, bool],
            default_arg1: bool=False,
            default_arg2: int = 0,
        ):
            pass
        deserialized = self._deserialize(
            listener_func, arg1={'Paul': False}, default_arg1=True)
        self.assertEqual(
            {'arg1': {'Paul': False}, 'default_arg1': True},
            deserialized,
        )

    def test_deserialize_3(self):
        def listener_func(
            *,
            arg1: datetime.date,
            arg2: Dict[datetime.date, bool],
            arg3: Dict[str, datetime.datetime],
        ):
            pass
        deserialized = self._deserialize(
            listener_func,
            arg1=datetime.date(2021, 1, 1),
            arg2={
                datetime.date(2021, 1, 7): True,
                datetime.date(2021, 1, 17): False,
            },
            arg3={'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
        )

        self.assertEqual(
            {'arg1': datetime.date(2021, 1, 1),
             'arg2': {datetime.date(2021, 1, 7): True, datetime.date(2021, 1, 17): False},
             'arg3': {'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
             },
            deserialized,
        )

    def test_deserialize_4(self):
        def listener_func(
            *,
            arg1: List[datetime.date],
            arg2: Set[float],
            arg3: Tuple[str],
        ):
            pass

        deserialized = self._deserialize(
            listener_func,
            arg1=[datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
            arg2={1.0, 2.1},
            arg3=('hello', 'world'),
        )
        self.assertEqual(
            {'arg1': [datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
             'arg2': {1.0, 2.1},
             'arg3': ('hello', 'world'),
             },
            deserialized,
        )

    def _deserialize(self, callback, **kwargs):
        channel = CustomPayloadChannel(callback)
        serialized = _serialize(**kwargs)
        return channel.deserialize(serialized)
