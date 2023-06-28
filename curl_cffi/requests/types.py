import typing

HeaderTypes = typing.Union[
    "Headers",
    typing.Mapping[str, str],
    typing.Mapping[bytes, bytes],
    typing.Sequence[typing.Tuple[str, str]],
    typing.Sequence[typing.Tuple[bytes, bytes]],
    typing.Sequence[str],
    typing.Sequence[bytes],
]
