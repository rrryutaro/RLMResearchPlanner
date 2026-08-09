__version__ = "0.0.16"
__build__ = 1
__dev__ = False


def version_string() -> str:
    if __dev__:
        return f"{__version__}+b{__build__}"
    return __version__
