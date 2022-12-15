import contextlib
import importlib.util
import json
import os.path
import sys

from zipfile import ZipFile
from mcdreforged.api.utils import Serializable
from mcdreforged.api.types import VersionRequirement
from typing import *
from parse import parse


# Configuration
TARGET_PLUGIN_FILENAME_PATTERN = [
    'rue.mcdr'
]   # e.g. PluginName.mcdr/pyz PluginName-v{}.mcdr/pyz
ACCEPT_MULTIPLE_MATCH = False  # If allowed, this will load the first matched
# End Config
# DO NOT Edit the stuffs below unless you know what you are doing!

METADATA_FILE_NAME = 'mcdreforged.plugin.json'


class DifferentMetadata(Serializable):
    cbr_dependencies: Dict[str, str]
    cbr_entrypoint: str

    @property
    def cbr_part(self):
        data, ret = self.serialize(), {}
        for key, value in data.items():
            ret[key[4:]] = value
        return ret


class CBRMetadata(Serializable):
    id: str
    name: str
    version: str
    description: Union[str, Dict[str, str]]
    author: Union[str, List[str], None]
    link: Optional[str]
    dependencies: Dict[str, str]

    entrypoint: str  # Actually not exists

    @property
    def entry(self):
        return self.serialize().get('entrypoint', self.id)


class TargetMCDRPlugin:
    def __init__(self, path: str):
        self._path = path
        self.__spec = None
        self.instance = None
        self.__metadata: Optional[CBRMetadata] = None

    @contextlib.contextmanager
    def open_bundled_file(self, path: str):
        raise NotImplementedError

    def get_metadata(self) -> CBRMetadata:
        if self.__metadata is None:
            self.__metadata = self._get_metadata()
        return self.__metadata

    def _get_metadata(self) -> CBRMetadata:
        with self.open_bundled_file(METADATA_FILE_NAME) as file:
            data = json.load(file)
        if 'id' not in data:
            data['id'] = os.path.basename(self._path).rsplit('.', maxsplit=1)[0]
        if 'dependencies' in data.keys():
            del data['dependencies']
        if 'entrypoint' in data.keys():
            del data['entrypoint']
        meta, diff = CBRMetadata.deserialize(data), DifferentMetadata.deserialize(data)
        meta.update_from(diff.cbr_part)
        if isinstance(meta.description, dict):
            meta.description = list(meta.description.values())[0]
        return meta

    def import_entrypoint(self):
        sys.path.append(self._path)
        meta = self.get_metadata()
        target_module = importlib.import_module(meta.entry)

        module_dict = target_module.__dict__
        try:
            to_import = target_module.__all__
        except AttributeError:
            to_import = [name for name in module_dict if not name.startswith('_')]
        globals().update({name: module_dict[name] for name in to_import})

    def unload(self):
        if self._path in sys.path:
            sys.path.remove(self._path)
        self.__spec = None
        self.instance = None


class ZipPlugin(TargetMCDRPlugin):
    @contextlib.contextmanager
    def open_bundled_file(self, path: str):
        with ZipFile(self._path).open(path) as file:
            yield file


class FolderPlugin(TargetMCDRPlugin):
    @contextlib.contextmanager
    def open_bundled_file(self, path: str):
        with open(os.path.join(self._path, path), encoding='utf8') as file:
            yield file


PLUGIN_DIR = 'plugins'
matched = []
for file_name in os.listdir(PLUGIN_DIR):
    for pattern in TARGET_PLUGIN_FILENAME_PATTERN:
        if parse(pattern, file_name) is not None:
            matched.append(os.path.join(PLUGIN_DIR, file_name))

if len(matched) == 0:
    os.remove(__file__)
    raise FileNotFoundError('Target plugin not found')
elif len(matched) > 1 and not ACCEPT_MULTIPLE_MATCH:
    raise RuntimeError('Multiple target plugin found')
else:
    target_plugin = matched[0]
    if not os.path.exists(target_plugin):
        raise FileNotFoundError('Target plugin moved or damaged')
    elif os.path.isdir(target_plugin):
        plugin_inst = FolderPlugin(target_plugin)
    else:
        plugin_inst = ZipPlugin(target_plugin)

METADATA = plugin_inst.get_metadata().serialize()
plugin_inst.import_entrypoint()
