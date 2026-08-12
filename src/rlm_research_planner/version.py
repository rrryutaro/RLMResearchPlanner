__version__ = "0.1.3"
__build__ = 10
__dev__ = False


def version_string() -> str:
    if __dev__:
        return f"{__version__}+b{__build__}"
    return __version__
