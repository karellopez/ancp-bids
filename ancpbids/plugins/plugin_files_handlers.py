from typing import Optional

from ancpbids.plugin import FileHandlerPlugin


def read_yaml(file_path: str, **kwargs):
    import yaml
    with open(file_path, 'r') as stream:
        try:
            return yaml.load(stream, Loader=yaml.FullLoader)
        except:
            return None


def read_json(file_path: str, **kwargs):
    """Reads a JSON file used by lazy loading.

    Large files are accessed via ``mmap`` to keep memory usage low when file
    contents are only needed transiently.
    """
    import json
    import mmap
    with open(file_path, "r") as stream:
        try:
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                return json.loads(mm.read().decode())
        except Exception:
            return None


def read_plain_text(file_path: str, **kwargs):
    with open(file_path, 'r') as file:
        return file.readlines()


def read_tsv(file_path: str, return_type: Optional[str] = None, **kwargs):
    if return_type == "ndarray":
        import numpy

        return numpy.genfromtxt(
            file_path, delimiter='\t', dtype=None, names=True
        )
    elif return_type == "dataframe":
        import pandas

        return pandas.read_csv(file_path, delimiter='\t')
    else:
        import csv

        with open(file_path) as f:
            return list(csv.DictReader(f, dialect="excel-tab"))


def write_json(file_path: str, contents: dict, **kwargs):
    """Writes the contents as a .json file to the given file path.

    Parameters
    ----------
    file_path:
        The path to the file to store the contents to.
    contents:
        The contents of the target .json file.

    """
    import json
    with open(file_path, 'w') as fp:
        json.dump(contents, fp, indent=2)

def write_txt(file_path: str, contents: dict, **kwargs):
    """Writes the contents as a .txt file to the given file path.

    Parameters
    ----------
    file_path:
        The path to the file to store the contents to.
    contents:
        The contents of the target .txt file.

    """
    with open(file_path, 'w') as fp:
        fp.write(str(contents))


class FilesHandlerPlugin(FileHandlerPlugin):
    def execute(self, file_readers_registry, file_writers_registry):
        file_readers_registry['yaml'] = read_yaml
        file_readers_registry['json'] = read_json
        file_readers_registry['txt'] = read_plain_text
        file_readers_registry['tsv'] = read_tsv

        file_writers_registry['json'] = write_json
        file_writers_registry['txt'] = write_txt
