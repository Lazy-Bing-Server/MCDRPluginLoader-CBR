
import json as _js
import os as _os
import sys as _sys
import importlib as _iml
import typing as _typ

from contextlib import contextmanager as _cttm
from zipfile import ZipFile as _ZipFile
from mcdreforged.api.utils import Serializable as _Serializable

from parse import parse as _parse


# Configuration
_TARGET_PLUGIN_FILENAME_PATTERN = [
    'rue.mcdr'
]   # e.g. PluginName.mcdr/pyz PluginName-v{}.mcdr/pyz
_ACCEPT_MULTIPLE_MATCH = False  # If allowed, this will load the first matched
# End Config
# DO NOT Edit the stuffs below unless you know what you are doing!

_METADATA_FILE_NAME = 'mcdreforged.plugin.json'
_PLUGIN_DIR = 'plugins'


class _CBRCompatiableMetadata(_Serializable):
    id: _typ.Optional[str] = None
    name: str
    version: str
    description: _typ.Union[str, _typ.Dict[str, str]]
    author: _typ.Union[str, _typ.List[str], None]
    link: _typ.Optional[str]
    cbr_dependencies: _typ.Dict[str, str]

    cbr_entrypoint: str  # Actually not exists

    def get_meta(self, file: str):
        if self.id is None:
            self.id = file.rsplit('.', maxsplit=1)[0]
        if isinstance(self.description, dict):
            self.description = list(self.description.values())[0]
        ret = {}
        for key, value in self.serialize().items():
            if key.startswith('cbr_'):
                key = key [4:]
            ret[key] = value
        return ret


class _TargetMCDRPlugin:
    def __init__(self, path: str):
        self._path = path
        self.instance = None
        self.__metadata: _typ.Optional[dict] = None

    @_cttm
    def open_bundled_file(self, path: str):
        raise NotImplementedError

    def get_metadata(self) -> dict:
        if self.__metadata is None:
            self.__metadata = self._get_metadata()
        return self.__metadata

    def _get_metadata(self) -> dict:
        with self.open_bundled_file(_METADATA_FILE_NAME) as file:
            data: dict = _js.load(file)
        meta = _CBRCompatiableMetadata.deserialize(data)
        return meta.get_meta(_os.path.basename(self._path))

    def import_entrypoint(self):
        _sys.path.append(self._path)
        meta = self.get_metadata()
        target_module = _iml.import_module(meta['entrypoint'])

        module_dict = target_module.__dict__
        try:
            to_import = target_module.__all__
        except AttributeError:
            to_import = [name for name in module_dict if not name.startswith('_')]
        globals().update({name: module_dict[name] for name in to_import})

    def unload(self):
        if self._path in _sys.path:
            _sys.path.remove(self._path)
        self.instance = None


class _ZipPlugin(_TargetMCDRPlugin):
    @_cttm
    def open_bundled_file(self, path: str):
        with _ZipFile(self._path).open(path) as file:
            yield file


class _FolderPlugin(_TargetMCDRPlugin):
    @_cttm
    def open_bundled_file(self, path: str):
        with open(_os.path.join(self._path, path), encoding='utf8') as file:
            yield file


def __load_plugin() -> _TargetMCDRPlugin:
    matched = []
    for file_name in _os.listdir(_PLUGIN_DIR):
        for pattern in _TARGET_PLUGIN_FILENAME_PATTERN:
            if _parse(pattern, file_name) is not None:
                matched.append(_os.path.join(_PLUGIN_DIR, file_name))

    if len(matched) == 0:
        _os.remove(__file__)
        raise FileNotFoundError('Target plugin not found')
    elif len(matched) > 1 and not _ACCEPT_MULTIPLE_MATCH:
        raise RuntimeError('Multiple target plugin found')
    else:
        target_plugin = matched[0]
        if not _os.path.exists(target_plugin):
            raise FileNotFoundError('Target plugin moved or damaged')
        elif _os.path.isdir(target_plugin):
            plugin_inst = _FolderPlugin(target_plugin)
        else:
            plugin_inst = _ZipPlugin(target_plugin)
    return plugin_inst

__inst = __load_plugin()

METADATA = __inst.get_metadata()
__inst.import_entrypoint()
