import fnmatch
import inspect
import math
import os
import sys
from difflib import SequenceMatcher

from ancpbids.plugin import SchemaPlugin
from ancpbids.query import Select, query, query_entities
from ancpbids.utils import resolve_segments, convert_to_relative
from ancpbids.model_base import *


def has_entity(artifact, entity_):
    for e in artifact.entities:
        if e.key == entity_:
            return True
    return False


def get_entity(artifact, entity_):
    for e in artifact.entities:
        if e.key == entity_:
            return e.value
    return None


def add_entity(schema, artifact, key, value):
    if isinstance(key, schema.EntityEnum):
        key = key.entity_

    found = list(filter(lambda er: er.key == key, artifact.entities))
    if found:
        found[0].value = value
    else:
        eref = EntityRef(key, value)
        artifact.entities.append(eref)


def add_entities(schema, artifact, **kwargs):
    for k, v in kwargs.items():
        add_entity(schema, artifact, k, v)


def load_file_contents(folder, file_name, return_type: str = None):
    from ancpbids import utils
    file_path = get_absolute_path(folder, file_name)
    contents = utils.load_contents(file_path, return_type)
    return contents


def load_contents(file):
    from ancpbids import utils
    file_path = get_absolute_path(file.parent_object_, file.name)
    contents = utils.load_contents(file_path)
    return contents


def get_absolute_path_by_file(file):
    return get_absolute_path(file.parent_object_, file.name)


def get_absolute_path(folder, file_name=None):
    return _get_path(folder, file_name, True)


def _folder_get_relative_path(folder):
    return _get_path(folder, None, False)


def _file_get_relative_path(file):
    return _get_path(file.parent_object_, file.name, False)


def _get_path(folder, file_name=None, absolute=True):
    segments = []
    if file_name:
        segments.append(file_name)
    current_folder = folder
    while current_folder is not None:
        if isinstance(current_folder, Dataset):
            # prepend the dataset name if it is not part of the base dir name
            if not current_folder.base_dir_.endswith(current_folder.name):
                segments.insert(0, current_folder.name)
            if absolute:
                segments.insert(0, current_folder.base_dir_)
            # assume we reached the highest level, maybe not good for nested datasets
            break
        segments.insert(0, current_folder.name)
        current_folder = current_folder.parent_object_
    _path = os.path.join(*segments) if segments else ''
    _path = os.path.normpath(_path)
    if absolute:
        _path = os.path.abspath(_path)
    return _path


def remove_file(folder, file_name):
    folder.files = list(filter(lambda file: file.name != file_name, folder.files))


def create_artifact(folder, raw=None):
    artifact = Artifact()
    if isinstance(raw, Artifact):
        artifact.entities.extend(raw.entities)
    artifact.parent_object_ = folder
    folder.files.append(artifact)
    return artifact


def create_folder(folder, type_=None, **kwargs):
    if not type_:
        type_ = Folder
    sub_folder = type_(**kwargs)
    sub_folder.parent_object_ = folder
    folder.folders.append(sub_folder)
    return sub_folder


def create_derivative(ds, path=None, **kwargs):
    derivatives_folder = ds.derivatives
    if not ds.derivatives:
        derivatives_folder = DerivativeFolder()
        derivatives_folder.parent_object_ = ds
        derivatives_folder.name = "derivatives"
        ds.derivatives = derivatives_folder
    path = convert_to_relative(ds, path)
    target_folder, _ = resolve_segments(derivatives_folder, path, create_if_missing=True)
    derivative = DerivativeFolder(**kwargs)
    derivative.parent_object_ = target_folder
    target_folder.folders.append(derivative)

    derivative.dataset_description = DerivativeDatasetDescriptionFile()
    derivative.dataset_description.parent_object_ = derivative
    derivative.dataset_description.GeneratedBy = GeneratedBy()

    if ds.dataset_description:
        derivative.dataset_description.update(ds.dataset_description)

    return derivative


def create_dataset(schema, base_dir=None, **kwargs):
    ds = Dataset()
    ds._versioned_schema = schema
    ds.base_dir_ = base_dir
    ds.update(**kwargs)
    descr = DatasetDescriptionFile(name="dataset_description.json")
    descr.BIDSVersion = schema.VERSION
    descr.parent_object_ = ds
    ds.dataset_description = descr
    return ds


def get_file(folder, file_name):
    folder, file_name = resolve_segments(folder, file_name, True)
    if not folder:
        return None
    direct_files = folder.to_generator(depth_first=True, depth=1, filter_=lambda n: isinstance(n, File))
    file = next(filter(lambda f: f.name == file_name, direct_files), None)
    return file


def get_files(folder, name_pattern):
    direct_files = folder.to_generator(depth_first=True, depth=1, filter_=lambda n: isinstance(n, File))
    return list(filter(lambda file: fnmatch.fnmatch(file.name, name_pattern), direct_files))


def remove_folder(folder, folder_name):
    folder.folders = list(filter(lambda f: f.name != folder_name, folder.folders))


def get_folder(folder, folder_name):
    direct_folders = folder.to_generator(depth_first=True, depth=1, filter_=lambda n: isinstance(n, Folder))
    return next(filter(lambda f: f.name == folder_name, direct_folders), None)


def get_files_sorted(folder):
    return sorted(folder.files, key=lambda f: f.name)


def get_folders_sorted(folder):
    return sorted(folder.folders, key=lambda f: f.name)


def to_generator(source, depth_first=False, filter_=None, depth=1000):
    if depth < 0:
        return

    if not depth_first:
        if filter_ and not filter_(source):
            return
        yield source

    for key, value in source.items():
        if isinstance(value, Model):
            yield from to_generator(value, depth_first, filter_, depth - 1)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Model):
                    yield from to_generator(item, depth_first, filter_, depth - 1)

    if depth_first:
        if filter_ and not filter_(source):
            return
        yield source


def iterancestors(source):
    context = source
    while context is not None:
        if not hasattr(context, 'parent_object_'):
            break
        context = context.parent_object_
        yield context


def to_dict(source):
    return source


def get_model_classes(schema):
    if not hasattr(schema, '_CLASSES'):
        schema._CLASSES = {name: obj for name, obj in inspect.getmembers(schema) if inspect.isclass(obj)}
    return schema._CLASSES


def _get_element_members(schema, element_type):
    element_members = []
    try:
        members = element_type.MEMBERS
        element_members = list(
            map(lambda item: {'name': item[0], **item[1], 'type': _to_type(schema, item[1]['type'])},
                members.items()))
    except AttributeError as ae:
        pass
    return element_members


def get_members(schema, element_type, include_superclass=True):
    if element_type == schema.Model:
        return []
    super_members = []

    if include_superclass:
        superclass = element_type
        while True:
            try:
                mro = inspect.getmro(superclass)
                if len(mro) < 2:
                    break
                superclass = mro[1]
                if not superclass or superclass == schema.Model:
                    break
                super_members = super_members + _get_element_members(schema, superclass)
            except AttributeError:
                pass

    element_members = _get_element_members(schema, element_type)
    return super_members + element_members


def _to_type(schema, model_type_name: str):
    classes = schema.get_model_classes()
    if model_type_name in classes:
        return classes[model_type_name]
    if model_type_name in __builtins__:
        return __builtins__[model_type_name]
    return model_type_name


def _trim_int(value):
    try:
        # remove paddings/fillers in index values: 001 -> 1, 000230 -> 230
        # TODO return PaddedInt as done by PyBIDS
        return int(value)
    except ValueError:
        return value


def process_entity_value(schema, key, value):
    if not value:
        return value
    if isinstance(key, schema.EntityEnum):
        key = key.value['name']
    for sc_entity in filter(lambda e: e.value['name'] == key, schema.EntityEnum.__members__.values()):
        if sc_entity.value['format'] == 'index':
            if isinstance(value, list):
                return list(map(lambda v: _trim_int(v) if v is not None else v, value))
            else:
                return _trim_int(value)
    return value


def fuzzy_match_entity_key(schema, user_key):
    return fuzzy_match_entity(schema, user_key).value['name']


def fuzzy_match_entity(schema, user_key):
    ratios = list(
        map(lambda item: (
            item,
            1.0 if item.name.startswith(user_key) else SequenceMatcher(None, user_key,
                                                                       item.name).quick_ratio()),
            list(schema.EntityEnum)))
    ratios = sorted(ratios, key=lambda t: t[1])
    return ratios[-1][0]


def get_parent(file_or_folder):
    if hasattr(file_or_folder, 'parent_object_'):
        return file_or_folder.parent_object_
    return None


def select(context, target_type):
    return Select(context, target_type)


def get_entities(artifact):
    return {e['key']: e['value'] for e in artifact.entities}


def get_schema(model):
    current = model
    while current is not None:
        if isinstance(current, Dataset):
            return current._versioned_schema
        current = current.parent_object_
    return None


def get_sidecar_file(artifact, **entities):
    parent = artifact.get_parent()
    filters = dict(**artifact.get_entities())
    filters.update(**entities)
    return parent.query(**filters)


def _map_object(schema, model_type, json_object):
    target = model_type()
    members = schema.get_members(model_type, True)
    actual_props = json_object.keys()
    direct_props = list(map(lambda m: (m['name'], m), members))
    for prop_name, prop in direct_props:
        if prop_name in actual_props:
            value_type = prop['type']
            value = json_object[prop_name]
            if isinstance(value, list) and len(value) > 0:
                value = [
                    _map_object(schema, value_type, o) if isinstance(o, dict) else o
                    for o in value
                ]
            elif isinstance(value, dict):
                value = _map_object(schema, value_type, value)
            setattr(target, prop_name, value)
    return target


class PatchingSchemaPlugin(SchemaPlugin):
    def execute(self, schema):
        schema.Model.get_schema = get_schema
        schema.Model.__hash__ = lambda self: hash(tuple(self))
        schema.Folder.select = select
        schema.Folder.query = query
        schema.Folder.query_entities = query_entities
        schema.File.get_parent = get_parent
        schema.Folder.get_parent = get_parent
        schema.Artifact.has_entity = has_entity
        schema.Artifact.get_entity = get_entity
        schema.Artifact.get_entities = get_entities
        schema.Artifact.add_entity = lambda artifact, key, value: add_entity(schema, artifact, key, value)
        schema.Artifact.add_entities = lambda artifact, **kwargs: add_entities(schema, artifact, **kwargs)
        schema.Artifact.sidecar = get_sidecar_file
        schema.Folder.load_file_contents = load_file_contents
        schema.File.load_contents = load_contents
        schema.File.get_absolute_path = get_absolute_path_by_file
        schema.Folder.get_relative_path = _folder_get_relative_path
        schema.Folder.get_absolute_path = get_absolute_path
        schema.File.get_relative_path = _file_get_relative_path
        schema.Folder.remove_file = remove_file
        schema.Folder.create_artifact = create_artifact
        schema.Folder.create_folder = create_folder
        schema.Dataset.create_derivative = create_derivative
        schema.Folder.get_file = get_file
        schema.Folder.get_files = get_files
        schema.Folder.remove_folder = remove_folder
        schema.Folder.get_folder = get_folder
        schema.Folder.get_files_sorted = get_files_sorted
        schema.Folder.get_folders_sorted = get_folders_sorted
        schema.Model.to_generator = to_generator
        schema.Model.to_dict = to_dict
        schema.Model.iterancestors = iterancestors

        import weakref

        # ``weakref`` only works with objects supporting a weak reference slot.
        # The following thin wrappers allow us to cache list and dict instances
        # returned by ``load_contents`` via ``weakref.ref`` to enable automatic
        # cleanup once those objects are no longer referenced anywhere.
        class _RefableList(list):
            __slots__ = ('__weakref__',)

        class _RefableDict(dict):
            __slots__ = ('__weakref__',)

        def _lazy_contents_getter(self):
            """Lazily load the file's contents on first access.

            The value is cached using a weak reference so that memory is freed
            automatically once no reference to the contents exists anymore.
            """
            contents = self.get('contents')
            if contents is None:
                # try the weakref cache first
                ref = getattr(self, '_contents_ref', None)
                contents = ref() if ref else None
            if contents is None:
                # fall back to reading from disk
                try:
                    contents = self.load_contents()
                except Exception:
                    contents = None
                if isinstance(contents, list) and not isinstance(contents, _RefableList):
                    contents = _RefableList(contents)
                elif isinstance(contents, dict) and not isinstance(contents, _RefableDict):
                    contents = _RefableDict(contents)
                # store weak reference for future accesses
                self._contents_ref = weakref.ref(contents) if contents is not None else None
            return contents

        def _lazy_contents_setter(self, value):
            """Store file contents and update the weakref cache."""
            if isinstance(value, list) and not isinstance(value, _RefableList):
                value = _RefableList(value)
            elif isinstance(value, dict) and not isinstance(value, _RefableDict):
                value = _RefableDict(value)
            self._contents_ref = weakref.ref(value) if value is not None else None
            self['contents'] = value

        for cls in (schema.JsonFile, schema.MetadataFile,
                     schema.TSVFile, schema.TSVArtifact, schema.MetadataArtifact):
            cls.contents = property(_lazy_contents_getter, _lazy_contents_setter)

        def _lazy_ds_descr_getter(self):
            """Return dataset description loading the JSON file on demand."""
            descr = self.get('dataset_description')
            if descr is None:
                ref = getattr(self, '_ds_descr_ref', None)
                descr = ref() if ref else None
            if descr is None:
                file = self.get_file('dataset_description.json')
                if file:
                    json_obj = file.contents
                    if json_obj:
                        typ = self.get_schema().DatasetDescriptionFile
                        descr = _map_object(self.get_schema(), typ, json_obj)
                        descr.name = file.name
                        descr.contents = json_obj
                        descr.parent_object_ = self
                        self._ds_descr_ref = weakref.ref(descr)
            return descr

        def _lazy_ds_descr_setter(self, value):
            """Store dataset description and manage weakref cache."""
            if value is not None:
                self['dataset_description'] = value
                self._ds_descr_ref = weakref.ref(value)
            else:
                self['dataset_description'] = None
                self._ds_descr_ref = None

        def _lazy_deriv_descr_getter(self):
            """Derivative variant of the lazy dataset description getter."""
            descr = self.get('dataset_description')
            if descr is None:
                ref = getattr(self, '_ds_descr_ref', None)
                descr = ref() if ref else None
            if descr is None:
                file = self.get_file('dataset_description.json')
                if file:
                    json_obj = file.contents
                    if json_obj:
                        typ = self.get_schema().DerivativeDatasetDescriptionFile
                        descr = _map_object(self.get_schema(), typ, json_obj)
                        descr.name = file.name
                        descr.contents = json_obj
                        descr.parent_object_ = self
                        self._ds_descr_ref = weakref.ref(descr)
            return descr

        schema.Dataset.dataset_description = property(
            _lazy_ds_descr_getter, _lazy_ds_descr_setter
        )

        schema.DerivativeFolder.dataset_description = property(
            _lazy_deriv_descr_getter, _lazy_ds_descr_setter
        )

        schema.get_model_classes = lambda: get_model_classes(schema)
        schema.get_members = lambda element_type, include_superclass=True: get_members(schema, element_type,
                                                                                       include_superclass)
        schema.process_entity_value = lambda key, value: process_entity_value(schema, key, value)
        schema.fuzzy_match_entity_key = lambda user_key: fuzzy_match_entity_key(schema, user_key)
        schema.fuzzy_match_entity = lambda user_key: fuzzy_match_entity(schema, user_key)

        schema.create_dataset = lambda base_dir=None, **kwargs: create_dataset(schema, base_dir=base_dir, **kwargs)
