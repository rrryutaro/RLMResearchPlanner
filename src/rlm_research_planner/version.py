__version__ = "0.0.2"
__build__ = 7
__dev__ = False


def version_string() -> str:
    if __dev__:
        return f"{__version__}+b{__build__}"
    return __version__
