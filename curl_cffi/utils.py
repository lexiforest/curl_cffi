import warnings
from typing import Literal

HttpVersionLiteral = Literal["v1", "v2", "v2tls", "v2_prior_knowledge", "v3", "v3only"]

class CurlCffiWarning(UserWarning, RuntimeWarning):
    pass


def config_warnings(on: bool = False):
    if on:
        warnings.simplefilter("default", category=CurlCffiWarning)
    else:
        warnings.simplefilter("ignore", category=CurlCffiWarning)

